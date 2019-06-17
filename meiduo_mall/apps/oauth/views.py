import json
import re
from django import http
from django.conf import settings
from django.contrib.auth import login, authenticate
from django.shortcuts import render, redirect
from QQLoginTool.QQtool import OAuthQQ
from django.views import View
import logging
from django_redis import get_redis_connection
from meiduo_mall.utils.response_code import RETCODE
from users.models import User
from .models import OAuthQQuser, OAuthSinaUser
from .utils import generate_openid_signature, check_openid_signature, generate_uid_signature, check_uid_signature
from carts.utils import merge_cart_cookie_to_redis

from meiduo_mall.utils.sinaweibopy3 import APIClient

logger = logging.getLogger('django')

class QQAuthURLView(View):

    def get(self, request):
        # 获取查询参数中的next,获取用户从哪里去到login界面
        next = request.GET.get('next') or '/'

        # QQ_CLIENT_ID = '101518219'
        # QQ_CLIENT_SECRET = '418d84ebdc7241efb79536886ae95224'
        # QQ_REDIRECT_URI = 'http://www.meiduo.site:8000/oauth_callback'

        auth_qq = OAuthQQ(client_id=settings.QQ_CLIENT_ID,  # appid
                          client_secret=settings.QQ_CLIENT_SECRET,  # appkey
                          redirect_uri=settings.QQ_REDIRECT_URI,  # 登录成功之后回到美多的那个界面/回调地址
                          state=next)  # 记录界面跳转来源
        # 调用SDK中的get_qq_url方法得到拼接好的QQ登录url
        login_url = auth_qq.get_qq_url()
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'login_url': login_url})


class QQAuthView(View):
    """QQ登录成的回调处理"""

    def get(self, request):

        # 1.获取查询参数中的code
        code = request.GET.get('code')
        # 校验
        # 如果code没有获取到
        if code is None:
            return http.HttpResponseForbidden('缺少code')

        # 再次创建一个QQ登录的SDK对象
        auth_qq = OAuthQQ(client_id=settings.QQ_CLIENT_ID,  # appid
                          client_secret=settings.QQ_CLIENT_SECRET,  # appkey
                          redirect_uri=settings.QQ_REDIRECT_URI  # 登录成功之后回到美多的那个界面/回调地址
                          )
        try:
            # 调用SDK中的get_access_token(code)方法得到access_token
            access_token = auth_qq.get_access_token(code)
            # 调用SKD中的get_open_id(access_token)方法得到openid
            openid = auth_qq.get_open_id(access_token)
        except Exception as e:
            logger.error(e)
            return http.HttpResponseServerError('QQ的OAuth2.0认证失败')

        try:
            oauth_qq = OAuthQQuser.objects.get(openid=openid)
        except OAuthQQuser.DoesNotExist:

            openid = generate_openid_signature(openid)
            return render(request, 'oauth_callback.html', {'openid': openid})
        else:
            user = oauth_qq.user
            login(request, user)
            next = request.GET.get('state')
            response = redirect(next or '/')
            response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)

            # 在此就做合并购物车
            merge_cart_cookie_to_redis(request, response)
            return response

    def post(self, request):
        # 1.接收表单数据
        query_dict = request.POST
        mobile = query_dict.get('mobile')
        password = query_dict.get('password')
        sms_code = query_dict.get('sms_code')
        openid = query_dict.get('openid')

        # 校验
        if all([mobile, password, sms_code, openid]) is False:
            return http.HttpResponseForbidden('缺少必传参数')

        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('请输入5-20个字符的用户名')
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return http.HttpResponseForbidden('请输入8-20位的密码')

        redis_conn = get_redis_connection('verify_code')
        sms_code_server = redis_conn.get('sms_%s' % mobile)
        redis_conn.delete('sms_%s' % mobile)

        if sms_code_server is None:
            return http.HttpResponseForbidden('短信验证码过期')
        sms_code_server = sms_code_server.decode()
        if sms_code != sms_code_server:
            return http.HttpResponseForbidden('请输入正确的短信验证码')

        openid = check_openid_signature(openid)
        if openid is None:
            return http.HttpResponseForbidden('openid无效')

        try:
            user = User.objects.get(mobile=mobile)
        except User.DoesNotExist:
            user = User.objects.create_user(mobile=mobile, password=password, username=mobile)
        else:
            if user.check_password(password) is False:
                return render(request, 'oauth_callback.html', {'account_errmsg': '用户名或密码错误'})
        # openid和用户绑定
        OAuthQQuser.objects.create(
            openid=openid,
            user=user
        )

        login(request, user)
        next = request.GET.get('state')
        response = redirect(next or '/')
        response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)

        # 在此就做合并购物车
        merge_cart_cookie_to_redis(request, response)
        return response


class SinaAuthURLView(View):

    def get(self, request):
        # 获取查询参数中的next,获取用户从哪里去到login界面
        next = request.GET.get('next') or '/'

        # SINA_CLIENT_ID = '3305669385'
        # SINA_CLIENT_SECRET = '74c7bea69d5fc64f5c3b80c802325276'
        # SINA_REDIRECT_URI = 'http://www.meiduo.site:8000/sina_callback'

        auth_sina = APIClient(app_key=settings.SINA_CLIENT_ID,  # app_key
                          app_secret=settings.SINA_CLIENT_SECRET,  # app_id
                          redirect_uri=settings.SINA_REDIRECT_URI,  # 登录成功之后回到美多的那个界面/回调地址
                          )  # 记录界面跳转来源
        # 调用SDK中的get_authorize_url方法得到拼接好的sina微博登录url
        login_url = auth_sina.get_authorize_url()
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'login_url': login_url})


class SinaCallbackView(View):
    def get(self, request):
        return render(request, 'sina_callback.html')


class SinaCallback2View(View):
    def get(self, request):

        code = request.GET.get('code')
        if code is None:
            return http.HttpResponseForbidden('缺少code')
        client = APIClient(
            app_key=settings.SINA_CLIENT_ID,
            app_secret=settings.SINA_CLIENT_SECRET,
            redirect_uri=settings.SINA_REDIRECT_URI
        )

        try:
            token_dict = client.request_access_token(code)
            access_token = token_dict.access_token
        except Exception as e:
            logger.error(e)
            return http.HttpResponseForbidden('code无效')

        try:
            sina_u = OAuthSinaUser.objects.get(uid=access_token)
        except OAuthSinaUser.DoesNotExist:
            return http.JsonResponse({'access_token': access_token})
        else:
            user = sina_u.user
            data = {
                'user_id': user.id,
                'username': user.username,
                'token': access_token
            }
            login(request, user)
            response = http.JsonResponse(data)
            response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)
            merge_cart_cookie_to_redis(request, response)
            return response

    def post(self, request):
        jsondict = json.loads(request.body.decode())
        password = jsondict.get('password')
        mobile = jsondict.get('mobile')
        sms_code = jsondict.get('sms_code')
        access_token = jsondict.get('access_token')

        if not all([password, mobile, sms_code, access_token]):
            return http.HttpResponseForbidden('参数不全')

        try:
            user = User.objects.get(mobile=mobile)
        except User.DoesNotExist:
            return http.HttpResponseForbidden('用户不存在')
        user = authenticate(request, username=user.username, password=password)
        redis_conn = get_redis_connection('verify_code')
        sms_code_server = redis_conn.get('sms_%s' % mobile)
        print(sms_code_server)
        sms_code_server = sms_code_server.decode()
        if sms_code.lower() != sms_code_server.lower():
            return http.HttpResponseForbidden('验证码错误')

        oauth_sina = OAuthSinaUser.objects.create(user_id=user.id, uid=access_token)
        oauth_sina.save()

        context = {
            'token': access_token,
            'user_id': user.id,
            'username': user.username,
        }
        login(request, user)
        response = http.JsonResponse(context)
        response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)

        return response