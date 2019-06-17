from django.views import View
from django import http
from django_redis import get_redis_connection
import logging
from meiduo_mall.libs.captcha.captcha import captcha
from meiduo_mall.utils.response_code import RETCODE
from random import randint
from . import constants
from celery_tasks.sms.tasks import send_sms_code



# Create your views here.
logger = logging.getLogger('django')


class ImageCodeView(View):

    def get(self, request, uuid):

        name, text, image = captcha.generate_captcha()
        redis_conn = get_redis_connection('verify_code')
        redis_conn.setex('img_%s' % uuid, 300, text)

        return http.HttpResponse(image, content_type='image/png')


class SMSCodeView(View):

    def get(self, request, mobile):
        # 0 创建redis连接对象
        redis_conn = get_redis_connection('verify_code')
        # 0.1 尝试的去redis中获取此手机号有没发送过短信的标记,如果有,直接响应,获取不到返回None
        send_flag = redis_conn.get('send_flag_%s' % mobile)
        # 判断有没标记
        if send_flag:
            return http.JsonResponse({'code': RETCODE.THROTTLINGERR, 'errmsg': '频繁发送短信'})
        # 1. 提取前端url查询参数传入的image_code, uuid
        image_code_client = request.GET.get('image_code')
        uuid = request.GET.get('uuid')

        # 2. 校验 all()
        if all([image_code_client, uuid]) is False:
            return http.HttpResponseForbidden('缺少必传参数')

        # 2.1 获取redis中的图形验证码
        image_code_server = redis_conn.get('img_%s' % uuid)
        # 2.2 删除redis中图形验证码,让验证码只能用一次
        redis_conn.delete('img_%s' % uuid)
        #2.3 判断redis中存储的图形验证码是否已过期
        if image_code_server is None:
            return http.JsonResponse({'code': RETCODE.IMAGECODEERR, 'errmsg': '图形验证码已实效'})
        #2.4 从redis中取出来的数据都是bytes类型
        image_code_server = image_code_server.decode()
        #2.5 获取redis中的图形验证码 和前端传入的进行比较
        if image_code_client.lower() != image_code_server.lower():
            return http.JsonResponse({'code': RETCODE.IMAGECODEERR, 'errmsg': '请输入正确的图形验证码'})


        #3 生成一个随机的6位数字,作为短信验证码
        sms_code = '%06d' % randint(0, 999999)
        logger.info(sms_code)
        # 管道技术
        pl = redis_conn.pipeline()
        # 3.1 把短信验证码存储到redis,以备后期注册时校验
        # redis_conn.setex('sms_%s' % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        pl.setex('sms_%s' % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        # 3.1.2 向redis存储一个此手机号已发送过短信的标记
        # redis_conn.setex('send_flag_%s' % mobile, 60, 1)
        pl.setex('send_flag_%s' % mobile, 60, 1)
        # 执行管道
        pl.execute()
        # 3.2 发短信 容联云通讯
        # CCP().send_template_sms(mobile, [sms_code, constants.SMS_CODE_REDIS_EXPIRES//60], 1)
        send_sms_code.delay(mobile, sms_code)
        # 4. 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '发送短信验证码成功'})