from django.shortcuts import render
from django import http
from alipay import AliPay
import os
from django.conf import settings

from meiduo_mall.utils.views import LoginRequiredView
from orders.models import OrderInfo
from meiduo_mall.utils.response_code import RETCODE
from .models import Payment


class PaymentView(LoginRequiredView):

    def get(self, request, order_id):

        # 校验
        try:
            order = OrderInfo.objects.get(order_id=order_id, status=OrderInfo.ORDER_STATUS_ENUM['UNPAID'],
                                          user=request.user)
        except OrderInfo.DoesNotExist:
            return http.HttpResponseForbidden('订单有误')

        # 支付宝
        # ALIPAY_APPID = '2016091900551154'
        # ALIPAY_DEBUG = True  # 表示是沙箱环境还是真实支付环境
        # ALIPAY_URL = 'https://openapi.alipaydev.com/gateway.do'
        # ALIPAY_RETURN_URL = 'http://www.meiduo.site:8000/payment/status/'

        # 创建alipay SDK对象
        alipay = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,  # 默认回调url
            # /Users/chao/Desktop/meiduo_26/meiduo_mall/meiduo_mall/apps/payment/keys/appxxx.pem
            app_private_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys/app_private_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                'keys/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=settings.ALIPAY_DEBUG  # 默认False
        )

        # 调用sdk方法获取到 支付链接的查询参数
        # 电脑网站支付，需要跳转到https://openapi.alipaydev.com/gateway.do? + order_string
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,  # 美多订单编号
            total_amount=str(order.total_amount),  # 要支付的多少钱
            subject='美多商城:%s' % order_id,  # 支付时的注题
            return_url=settings.ALIPAY_RETURN_URL  # 支付成功后的回调url

        )

        # 拼接支付宝支付界面url
        # 沙箱支付环境: 'https://openapi.alipaydev.com/gateway.do' + '?' + order_string
        # 真实支付环境: 'https://openapi.alipay.com/gateway.do' + '?' + order_string
        alipay_url = settings.ALIPAY_URL + '?' + order_string

        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'alipay_url': alipay_url})


class PaymentStatusView(LoginRequiredView):
    """支付成功回调处理"""

    def get(self, request):
        # 1.接收查询参数中的所有数据
        query_dict = request.GET

        # 2.将查询参数QueryDict 转换成字典
        data = query_dict.dict()

        # 3.将字典中的sign 数据移除以备后期校验
        sign = data.pop('sign')

        # 4.创建alipay  SDK对象
        alipay = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,  # 默认回调url
            # /Users/chao/Desktop/meiduo_26/meiduo_mall/meiduo_mall/apps/payment/keys/appxxx.pem
            app_private_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys/app_private_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                'keys/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=settings.ALIPAY_DEBUG  # 默认False
        )

        # 5.调用aliPay中的verify方法
        success = alipay.verify(data, sign)
        if success:
            # 如果校验通过 获取到支付宝交易号和美多订单编号
            order_id = data.get('out_trade_no')
            trade_id = data.get('trade_no')

            # 将支付宝交易号和美多订单编号保存起来
            Payment.objects.create(
                order_id=order_id,
                trade_id=trade_id
            )
            # 修改已支付成功订单的状态
            OrderInfo.objects.filter(order_id=order_id, status=OrderInfo.ORDER_STATUS_ENUM['UNPAID']).update(
                status=OrderInfo.ORDER_STATUS_ENUM['UNCOMMENT']
            )
            # 响应  渲染支付结果界面
            return render(request, 'pay_success.html', {'trade_id': trade_id})
        else:
            # 如果支付结果校验失败,就响应其它
            return http.HttpResponseForbidden('非法请求')
