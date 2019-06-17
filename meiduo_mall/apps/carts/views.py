import json, pickle, base64

from django.shortcuts import render
from django import http
from django.views import View
from django_redis import get_redis_connection

from goods.models import SKU
from meiduo_mall.utils.response_code import RETCODE


class CartsView(View):
    """购物车"""

    def post(self, request):
        """购物车商品添加"""
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        count = json_dict.get('count')
        selected = json_dict.get('selected', True)

        if all([sku_id, count]) is False:
            return http.HttpResponseForbidden('缺少必傳參數')
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('類型有誤')

        user = request.user
        if user.is_authenticated:

            """
            hash: {sku_id_1: 1, sku_id_16: 2}
            set: {sku_id_1}
            """

            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            pl.hincrby('carts_%s' % user.id, sku_id, count)
            if selected:
                pl.sadd('selected_%s' % user.id, sku_id)
            pl.execute()
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '添加购物车成功'})

        else:
            """
            {
                sku_id_1: {'count': 1, 'selected': True},
                sku_id_2: {'count': 1, 'selected': True},
            }
            
            """
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                cart_str_bytes = cart_str.encode()
                cart_bytes = base64.b64decode(cart_str_bytes)
                cart_dict = pickle.loads(cart_bytes)
            else:
                cart_dict = {}
            if sku_id in cart_dict:
                origin_count = cart_dict[sku_id]['count']
                count += origin_count
            cart_dict[sku_id] = {
                'count': count,
                'selected': selected
            }

            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '添加购物车成功'})
            response.set_cookie('carts', cart_str)
            return response

    def get(self, request):
        """
        redis格式
        hash: {sku_id_1: 1, sku_id_16: 2}
        set: {sku_id_1}

        cookie格式
         {
            sku_id_1: {'count': 1, 'selected': True},
            sku_id_2: {'count': 1, 'selected': True},

        }
        """
        user = request.user
        if user.is_authenticated:
            redis_conn = get_redis_connection('carts')
            redis_dict = redis_conn.hgetall('carts_%s' % user.id)
            selected_ids = redis_conn.smembers('selected_%s' % user.id)
            cart_dict = {}
            for sku_id_bytes in redis_dict:
                cart_dict[int(sku_id_bytes)] = {
                    'count': int(redis_dict[sku_id_bytes]),
                    'selected': sku_id_bytes in selected_ids
                }
        else:
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                return render(request, 'cart.html')

        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        sku_list = []

        for sku_model in sku_qs:
            count = cart_dict[sku_model.id]['count']
            sku_list.append(
                {
                    'id': sku_model.id,
                    'name': sku_model.name,
                    'price': str(sku_model.price),
                    'default_image_url': sku_model.default_image.url,
                    'selected': str(cart_dict[sku_model.id]['selected']),
                    'count': count,
                    'amount': str(sku_model.price * count)
                }
            )
        return render(request, 'cart.html', {'cart_skus': sku_list})

    def put(self, request):

        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        count = json_dict.get('count')
        selected = json_dict.get('selected')

        if all([sku_id, count]) is False:
            return http.HttpResponseForbidden('缺少必传参数')

        try:
            sku_model = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id不存在')

        try:
            count = int(count)
        except Exception:
            return http.HttpResponseForbidden('类型有误')

        if isinstance(selected, bool) is False:
            return http.HttpResponseForbidden('类型有误')

        user = request.user
        if user.is_authenticated:

            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            pl.hset('carts_%s' % user.id, sku_id, count)
            if selected:
                pl.sadd('selected_%s' % user.id, sku_id)
            else:
                pl.srem('selected_%s' % user.id, sku_id)
            pl.execute()
            cart_sku = {
                'id': sku_model.id,
                'name': sku_model.name,
                'price': str(sku_model.price),
                'default_image_url': sku_model.default_image.url,
                'selected': selected,
                'count': count,
                'amount': str(sku_model.price * count)
            }

            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改购物车数据成功', 'cart_sku': cart_sku})
            return response

        else:
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': 'cookie数据没有获取到'})
            """
            {
                16: {'count': 2, 'selected': True}
            }
            """
            cart_dict[sku_id] = {
                'count': count,
                'selected': selected
            }
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            cart_sku = {
                'id': sku_model.id,
                'name': sku_model.name,
                'price': str(sku_model.price),
                'default_image_url': sku_model.default_image.url,
                'selected': selected,
                'count': count,
                'amount': str(sku_model.price * count)
            }

            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改购物车数据成功', 'cart_sku': cart_sku})
            response.set_cookie('carts', cart_str)
            return response

    def delete(self, request):
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id无效')
        user = request.user
        if user.is_authenticated:
            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            pl.hdel('carts_%s' % user.id, sku_id)
            pl.srem('selected_%s' % user.id, sku_id)
            pl.execute()
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': "删除购物车成功"})
        else:
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': 'cookie数据没获取到'})
            if sku_id in cart_dict:
                del cart_dict[sku_id]
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': "删除购物车成功"})
            if not cart_dict:
                response.delete_cookie('carts')
                return response

            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            response.set_cookie('carts', cart_str)
            return response

class CartsSelectedAllView(View):
    """购物车全选"""

    def put(self, request):

        json_dict = json.loads(request.body.decode())
        selected = json_dict.get('selected')

        if isinstance(selected, bool) is False:
            return http.HttpResponseForbidden('类型有误')
        user = request.user
        if user.is_authenticated:
            redis_conn = get_redis_connection('carts')
            redis_dict = redis_conn.hgetall('carts_%s' % user.id)
            if selected:
                redis_conn.sadd('selected_%s' % user.id, *redis_dict.keys())
            else:
                redis_conn.delete('selected_%s' % user.id)
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
        else:
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': 'cookie没有获取到'})
            for sku_id in cart_dict:
                cart_dict[sku_id]['selected'] = selected
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'cookie没有获取到'})

            for sku_id in cart_dict:
                cart_dict[sku_id]['selected'] = selected
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
            response.set_cookie('carts', cart_str)
            return response


class CartsSimpleView(View):
    """展示精简版购物车数据"""

    def get(self, request):
        # 判断用户是否登录
        """
            redis格式
            hash: {sku_id_1: 1, sku_id_16: 2}
            set: {sku_id_1}

            cookie格式
             {
                sku_id_1: {'count': 1, 'selected': True},
                sku_id_2: {'count': 1, 'selected': True},

            }
        """
        user = request.user
        if user.is_authenticated:
            redis_conn = get_redis_connection('carts')
            redis_dict = redis_conn.hgetall('carts_%s' % user.id)
            selected_ids = redis_conn.smembers('selected_%s' % user.id)

            cart_dict = {}
            for sku_id_bytes in redis_dict:
                cart_dict[int(sku_id_bytes)] = {
                    'count': int(redis_dict[sku_id_bytes]),
                    'selected': sku_id_bytes in selected_ids
                }

        else:
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                return render(request, 'cart.html')

        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        sku_list = []
        for sku_model in sku_qs:
            count = cart_dict[sku_model.id]['count']
            sku_list.append(
                {
                    'id': sku_model.id,
                    'name': sku_model.name,
                    'default_image_url': sku_model.default_image.url,
                    'count': count,
                }
            )
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'cart_skus': sku_list})