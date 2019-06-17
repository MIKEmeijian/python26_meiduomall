import json
from decimal import Decimal

from django import http
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from django_redis import get_redis_connection
from django.utils import timezone

from goods.models import SKU, GoodsCategory
from meiduo_mall.utils.response_code import RETCODE
from meiduo_mall.utils.views import LoginRequiredView
from users.models import Address
from .models import OrderInfo, OrderGoods
from django.core.paginator import Paginator, EmptyPage


class OrderSettlementView(LoginRequiredView):
    """去结算界面逻辑"""
    def get(self, request):
        addresses = Address.objects.filter(user=request.user, is_deleted=False)
        addresses = addresses if addresses.exists() else None
        user = request.user
        redis_conn = get_redis_connection('carts')
        redis_dict = redis_conn.hgetall('carts_%s' % user.id)
        selected_ids = redis_conn.smembers('selected_%s' % user.id)

        cart_dict = {}
        for sku_id_bytes in selected_ids:
            cart_dict[int(sku_id_bytes)] = int(redis_dict[sku_id_bytes])

        skus = SKU.objects.filter(id__in=cart_dict.keys())
        total_count = 0
        total_amount = Decimal('0.00')
        for sku in skus:
            sku.count = cart_dict[sku.id]
            sku.amount = sku.price * sku.count

            total_count += sku.count
            total_amount += sku.amount

        freight = Decimal('10.00')
        context = {
            'addresses': addresses,
            'skus': skus,
            'total_count': total_count,
            'total_amount': total_amount,
            'freight': freight,
            'payment_amount': total_amount + freight
        }

        return render(request, 'place_order.html', context)


class OrderCommitView(LoginRequiredView):
    """提交订单逻辑"""
    def post(self, request):
        json_dict = json.loads(request.body.decode())
        address_id = json_dict.get('address_id')
        pay_method = json_dict.get('pay_method')

        if all([address_id, pay_method]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            address = Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            return http.HttpResponseForbidden('address_id不存在')

        if pay_method not in [OrderInfo.PAY_METHODS_ENUM['CASH'], OrderInfo.PAY_METHODS_ENUM['ALIPAY']]:
            return http.HttpResponseForbidden('非法支付方式')

        user = request.user
        order_id = timezone.now().strftime('%Y%m%d%H%M%S') + ('%09d' % user.id)

        status = (OrderInfo.ORDER_STATUS_ENUM['UNPAID']
                  if pay_method == OrderInfo.PAY_METHODS_ENUM['ALIPAY']
                  else OrderInfo.ORDER_STATUS_ENUM['UNSEND'])

        with transaction.atomic():
            # 创建事务的保存点
            save_point = transaction.savepoint()
            try:
                # 保存订单记录
                order = OrderInfo.objects.create(
                    order_id=order_id,
                    user=user,
                    address=address,
                    total_count=0,
                    total_amount=Decimal('0.00'),
                    freight=Decimal('10.00'),
                    pay_method=pay_method,
                    status=status
                )

                redis_conn = get_redis_connection('carts')
                redis_dict = redis_conn.hgetall('carts_%s' % user.id)
                selected_ids = redis_conn.smembers('selected_%s' % user.id)

                cart_dict = {}
                for sku_id_bytes in selected_ids:
                    cart_dict[int(sku_id_bytes)] = int(redis_dict[sku_id_bytes])

                for sku_id in cart_dict:
                    while True:
                        sku = SKU.objects.get(id=sku_id)
                        buy_count = cart_dict[sku_id]
                        origin_stock = sku.stock
                        origin_sales = sku.sales

                        if buy_count > origin_stock:
                            transaction.savepoint_rollback(save_point)
                            return http.JsonResponse({'code': RETCODE.STOCKERR, 'errmsg': '库存不足'})

                        new_stock = origin_stock - buy_count
                        new_sales = origin_sales + buy_count
                        result = SKU.objects.filter(id=sku_id, stock=origin_stock).update(stock=new_stock, sales=new_sales)


                        if result == 0:
                            continue

                        spu = sku.spu
                        spu.sales += buy_count
                        spu.save()

                        OrderGoods.objects.create(
                            order=order,
                            sku=sku,
                            count=buy_count,
                            price=sku.price
                        )
                        order.total_count += buy_count
                        order.total_amount += (sku.price * buy_count)
                        break

                order.total_amount += order.freight
                order.save()

            except Exception:
                transaction.savepoint_rollback(save_point)
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': '下单失败'})

            else:
                transaction.savepoint_commit(save_point)

        pl = redis_conn.pipeline()
        pl.hdel('carts_%s' % user.id, *selected_ids)
        pl.delete('selected_%s' % user.id)
        pl.execute()

        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '下单成功', 'order_id': order_id})


class OrderSuccessView(LoginRequiredView):

    def get(self, request):
        query_dict = request.GET
        order_id = query_dict.get('order_id')
        payment_amount = query_dict.get('payment_amount')
        pay_method = query_dict.get('pay_method')

        try:
            OrderInfo.objects.get(order_id=order_id, pay_method=pay_method, total_amount=payment_amount)
        except OrderInfo.DoesNotExist:
            return http.HttpResponseForbidden('订单信息有误')

        context = {
            'order_id': order_id,
            'pay_method': pay_method,
            'payment_amount': payment_amount
        }

        return render(request, 'order_success.html', context)


class GoodsOrdersView(LoginRequiredView):
    """全部订单"""
    def get(self, request, page_num):

        user = request.user
        # 获取当前登录用户的所有订单按时间降序排序
        order_qs = OrderInfo.objects.filter(user=user).order_by('-create_time')
        # 创建分页对象Paginator(要分页的所有数据, 每页显示多个条数据)
        paginator = Paginator(order_qs, 5)
        try:
            # 获取指定页的订单数据
            page_orders = paginator.page(page_num)
        except EmptyPage:
            return http.HttpResponseForbidden('当前页不存在')
        # 获取总页数据
        total_page = paginator.num_pages
        # 获取每个order对象
        for order in page_orders:
            # 订单支付方式
            order.pay_method_name = OrderInfo.PAY_METHOD_CHOICES[order.pay_method-1][1]
            # 订单状态
            order.status_name = OrderInfo.ORDER_STATUS_CHOICES[order.status-1][1]
            # 获取所有当前的订单的商品
            goods = order.skus.all()
            # 给order增加sku_list属性
            order.sku_list = []
            for good in goods:
                sku = good.sku
                sku.count = good.count
                sku.amount = good.price * good.count
                order.sku_list.append(sku)

        context = {
            'page_orders': page_orders,  # 分页后数据
            'total_page': total_page,  # 总页数
            'page_num': page_num,  # 当前页码
        }

        return render(request, 'user_center_order.html', context)


class OrderCommentView(LoginRequiredView):

    def get(self, request):
        order_id = request.GET.get('order_id')
        try:
            order = OrderInfo.objects.get(order_id=order_id)
        except OrderInfo.DoesNotExist:
            return http.HttpResponseForbidden('订单信息有误')

        goods = order.skus.filter(is_commented=False)
        skus = []
        for good in goods:
            sku = good.sku
            skus.append({
                'order_id': order_id,
                'sku.id': good.id,
                'default_image_url': sku.default_image.url,
                'name': sku.name,
                'price': str(sku.price)
            })
        json_skus = json.dumps(skus)
        context = {
            'uncomment_goods_list': json_skus
        }
        return render(request, 'goods_judge.html', context)


    def post(self, request):
        json_dict = json.loads(request.body.decode())
        order_id = json_dict.get('order_id')
        sku_id = json_dict.get('sku_id')
        comment = json_dict.get('comment')
        score = json_dict.get('score')
        is_anonymous = json_dict.get('is_anonymous')

        if not all([order_id, sku_id, comment, score]):
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            order = OrderInfo.objects.get(order_id=order_id)
        except OrderInfo.DoesNotExist:
            return http.HttpResponseForbidden("缺少订单参数")
        try:
            order_good = OrderGoods.objects.get(id=sku_id)
        except SKU.DoesNotExist as e:
            return JsonResponse({'code': RETCODE.DBERR, 'errmsg': 'sku_id有误'})
        # 判断is_anonymous
        if isinstance(is_anonymous, bool) is False:
            return JsonResponse({'code': RETCODE.DBERR, 'errmsg': 'is_anonymous参数有误'})

        # 保存订单商品数据
        order_good.comment = comment
        order_good.score = score
        order_good.is_anonymous = is_anonymous
        order_good.is_commented = True
        order_good.save()

        # 增加商品sku评价数量
        sku = order_good.sku
        sku.comments += 1
        sku.save()

        order_goods = order.skus.all()
        # 修改订单状态
        order.status = OrderInfo.ORDER_STATUS_CHOICES[4][0]
        for each_good in order_goods:
            if not each_good.is_commented:
                order.status = OrderInfo.ORDER_STATUS_CHOICES[3][0]
                break
        # 保存订单状态
        order.save()

        # 响应
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})



