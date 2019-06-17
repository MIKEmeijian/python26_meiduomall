from django.shortcuts import render, redirect
from django.views import View
from django import http
import re, json
from django.contrib.auth import login, authenticate, logout, mixins
from django_redis import get_redis_connection
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from goods.models import SKU
from .models import User, Address
from meiduo_mall.utils.response_code import RETCODE
from celery_tasks.email.tasks import send_verify_email
from .utils import generate_email_verify_url, check_verify_token, get_user_by_account
from meiduo_mall.utils.views import LoginRequiredView
import logging
from carts.utils import merge_cart_cookie_to_redis

from itsdangerous import TimedJSONWebSignatureSerializer as Serializer, BadData
from random import randint
from verifications import constants
from celery_tasks.sms.tasks import send_sms_code

logger = logging.getLogger('django')


class RegisterView(View):
    """用户注册"""

    def get(self, request):

        return render(request, 'register.html')

    def post(self, request):

        query_dict = request.POST
        username = query_dict.get('username')
        password = query_dict.get('password')
        password2 = query_dict.get('password2')
        mobile = query_dict.get('mobile')
        sms_code = query_dict.get('sms_code')
        allow = query_dict.get('allow')

        if all([username, password, password2, mobile, sms_code, allow]) is False:
            return http.HttpResponseForbidden('缺少必传参数')

        if not re.match(r'^[a-zA-Z0-9_-]{5,20}$', username):
            return http.HttpResponseForbidden('请输入5-20字符的用户名')

        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return http.HttpResponseForbidden('请输入8-20位的密码')

        if not re.match(r'^[0-9A-Za-z]{8,20}$', password2):
            return http.HttpResponseForbidden('两次输入的密码不一致')

        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('请输入11位手机号')

        # 2.1 短信验证码后期再补充校验逻辑
        redis_conn = get_redis_connection('verify_code')
        # 2.2 获取redis中的短信验证码
        sms_code_server = redis_conn.get('sms_%s' % mobile)
        # 2.3 删除redis中的短信验证码,让验证码只能用一次
        redis_conn.delete('sms_%s' % mobile)

        # 2.4 校验短信验证码是否过期
        if sms_code_server is None:
            return http.HttpResponseForbidden('短信验证码过期')
        # 2.5 把bytes类型转换成字符串
        sms_code_server = sms_code_server.decode()
        # 2.6 判断前端和后端的短信验证码是否一致
        if sms_code != sms_code_server:
            return http.HttpResponseForbidden('请输入正确的短信验证码')

        user = User.objects.create_user(username=username, password=password, mobile=mobile)

        login(request, user)

        return redirect('/')


class UsernameCountView(View):
    """判断用户名是否重复注册"""

    def get(self, reuquest, username):
        count = User.objects.filter(username=username).count()
        response_data = {'count': count, 'code': RETCODE.OK, 'errmsg': 'OK'}
        return http.JsonResponse(response_data)


class MobileCountView(View):
    """判断手机号是否重复注册"""

    def get(self, request, mobile):
        count = User.objects.filter(mobile=mobile).count()
        response_data = {'count': count, 'code': RETCODE.OK, 'errmsg': 'OK'}
        return http.JsonResponse(response_data)


class LoginView(View):
    """用户登录"""

    def get(self, request):

        return render(request, 'login.html')

    def post(self, request):

        username = request.POST.get('username')
        password = request.POST.get('password')
        remembered = request.POST.get('remembered')
        # 多账号登录简化版
        # if re.match(r'^1[3-9]\d{9}$', username):
        #     User.USERNAME_FIELD = 'mobile'

        user = authenticate(request, username=username, password=password)
        # User.USERNAME_FIELD = 'username'

        if user is None:
            return render(request, 'login.html', {'account_errmsg': '用户名或密码错误'})

        login(request, user)

        if remembered != 'on':
            request.session.set_expiry(0)

        next = request.GET.get('next')
        response = redirect(next or '/')
        response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE if remembered else None)
        # 在此就做合并购物车
        merge_cart_cookie_to_redis(request, response)
        return response


class LogoutView(View):
    """退出登录"""

    def get(self, request):
        # 1.清除状态保持信息（清除session里面的uuid)
        logout(request)
        # 2.创建响应对象重定向到登录页
        response = redirect('/login/')
        # 3.清除cookie中的username
        response.delete_cookie('username')
        # 4.响应
        return response


# class UserInfoView(View):
#
#
#     def get(self, request):
#
#         user = request.user
#         if user.is_authenticated:
#             return render(request, 'user_center_info.html')
#         else:
#             return redirect('/login/?next=/info/')


# class UserInfoView(View):
#     @method_decorator(login_required)
#     def get(self, request):
#         return render(request, 'user_center_info.html')


class UserInfoView(mixins.LoginRequiredMixin, View):
    """展示用户中心"""

    def get(self, request):
        return render(request, 'user_center_info.html')


class EmailView(mixins.LoginRequiredMixin, View):
    """设置用户邮箱"""

    def put(self, request):

        json_dict = json.loads(request.body.decode())
        email = json_dict.get('email')

        if not email:
            return http.JsonResponse({'code': RETCODE.NECESSARYPARAMERR, 'errmsg': '缺少email参数'})
        if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return http.JsonResponse({'code': RETCODE.EMAILERR, 'errmsg': '邮箱格式错误'})
        user = request.user
        User.objects.filter(username=user.username, email='').update(email=email)

        verify_url = generate_email_verify_url(user)
        send_verify_email.delay(email, verify_url)

        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '添加邮箱成功'})


class VerifyEmailView(View):
    """激活邮箱"""

    def get(self, request):

        token = request.GET.get('token')
        if token is None:
            return http.HttpResponseForbidden('缺少token')
        user = check_verify_token(token)
        if user is None:
            return http.HttpResponseForbidden('token无效')

        user.email_active = True
        user.save()
        return redirect('/info/')


class AddressView(LoginRequiredView):
    """用户收货地址"""

    def get(self, request):
        user = request.user
        address_qs = Address.objects.filter(user=user, is_deleted=False)
        addresses = []
        for address_model in address_qs:
            addresses.append({
                'id': address_model.id,
                'title': address_model.title,
                'receiver': address_model.receiver,
                'province': address_model.province.name,
                "province_id": address_model.province.id,
                "city": address_model.city.name,
                "city_id": address_model.city.id,
                "district": address_model.district.name,
                "district_id": address_model.district.id,
                "place": address_model.place,
                "mobile": address_model.mobile,
                "tel": address_model.tel,
                "email": address_model.email
            })

        context = {
            'addresses': addresses,
            'default_address_id': user.default_address_id
        }
        return render(request, 'user_center_site.html', context)


class CreateAddressView(LoginRequiredView):
    """收货地址新增"""

    def post(self, request):

        user = request.user
        count = Address.objects.filter(user=user, is_deleted=False).count()
        if count >= 20:
            return http.JsonResponse({'code': RETCODE.THROTTLINGERR, 'errmsg': '收货超过上限'})
        json_dict = json.loads(request.body.decode())

        title = json_dict.get('title')
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')

        if all([title, receiver, province_id, city_id, district_id, place, mobile]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return http.HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return http.HttpResponseForbidden('参数email有误')

        try:
            address_model = Address.objects.create(
                user=request.user,
                title=title,
                receiver=receiver,
                province_id=province_id,
                city_id=city_id,
                district_id=district_id,
                place=place,
                mobile=mobile,
                tel=tel,
                email=email
            )
        except Exception as e:
            logger.error(e)
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '新增收获地址失败'})

        if user.default_address is None:
            user.default_address = address_model
            user.save()

        address_dict = {
            'id': address_model.id,
            'title': address_model.title,
            'receiver': address_model.receiver,
            'province': address_model.province.name,
            'province_id': address_model.province.id,
            'city': address_model.city.name,
            'city_id': address_model.city.id,
            'district': address_model.district.name,
            "district_id": address_model.district.id,
            "place": address_model.place,
            "mobile": address_model.mobile,
            "tel": address_model.tel,
            "email": address_model.email
        }

        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '新增地址成功', 'address': address_dict})


class UpdateDestroyAddressView(LoginRequiredView):
    """修改和删除用户收货地址"""

    def put(self, request, address_id):
        # 接收请求体数据
        json_dict = json.loads(request.body.decode())
        title = json_dict.get('title')
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')
        # 校验
        if all([title, receiver, province_id, city_id, district_id, place, mobile]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return http.HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return http.HttpResponseForbidden('参数email有误')

        try:
            # 修改收货地址数据
            Address.objects.filter(id=address_id).update(
                title=title,
                receiver=receiver,
                province_id=province_id,
                city_id=city_id,
                district_id=district_id,
                place=place,
                mobile=mobile,
                tel=tel,
                email=email
            )
        except Exception as e:
            logger.error(e)
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '修改收货地址失败'})

        # 获取到修改后的地址模型对象
        address_model = Address.objects.get(id=address_id)
        address_dict = {
            'id': address_model.id,
            'title': address_model.title,
            "receiver": address_model.receiver,
            "province": address_model.province.name,
            "province_id": address_model.province.id,
            "city": address_model.city.name,
            "city_id": address_model.city.id,
            "district": address_model.district.name,
            "district_id": address_model.district.id,
            "place": address_model.place,
            "mobile": address_model.mobile,
            "tel": address_model.tel,
            "email": address_model.email
        }
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改地址成功', 'address': address_dict})

    def delete(self, request, address_id):
        """删除收货地址"""
        try:
            address = Address.objects.get(id=address_id)
            address.is_deleted = True
            address.save()
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '删除地址成功'})
        except Address.DoesNotExist:
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': 'address_id不存在'})


class DefaultAddressView(LoginRequiredView):
    """设置默认收货地址"""

    def put(self, request, address_id):

        try:
            address = Address.objects.get(id=address_id)
            user = request.user
            user.default_address = address
            user.save()

            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '设置默认地址成功'})
        except Address.DoesNotExist:
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '设置默认地址失败'})


class UpdateTitleAddressView(LoginRequiredView):
    """修改用户收货地址标题"""

    def put(self, request, address_id):

        json_dict = json.loads(request.body.decode())
        title = json_dict.get('title')

        if title is None:
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '缺少必传参数'})

        try:
            address = Address.objects.get(id=address_id)
            address.title = title
            address.save()

            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改地址标题成功'})
        except Address.DoesNotExist:
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '修改地址标题失败'})


class ChangePasswordView(LoginRequiredView):
    """修改用户密码"""

    def get(self, request):
        return render(request, 'user_center_pass.html')

    def post(self, request):

        query_dict = request.POST
        old_password = query_dict.get('old_pwd')
        new_password = query_dict.get('new_pwd')
        new_password2 = query_dict.get('new_cpwd')

        if all([old_password, new_password, new_password2]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        user = request.user
        if user.check_password(old_password) is False:
            return render(request, 'user_center_pass.html', {'origin_pwd_errmsg': '原密码错误'})
        if not re.match(r'^[0-9A-Za-z]{8,20}$', new_password):
            return http.HttpResponseForbidden('密码最少8位,最长20位')
        if new_password != new_password2:
            return http.HttpResponseForbidden('两次输入的密码不一致')

        user.set_password(new_password)
        user.save()
        logout(request)
        response = redirect('/login/')
        response.delete_cookie('username')
        return response


class UserBrowseHistory(LoginRequiredView):
    """商品浏览记录"""

    def post(self, request):
        """保存浏览记录逻辑"""
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')

        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id不存在')

        redis_conn = get_redis_connection('history')
        pl = redis_conn.pipeline()
        user = request.user
        key = 'history_%s' % user.id
        # 先去重
        pl.lrem(key, 0, sku_id)
        # 添加到列表的开头
        pl.lpush(key, sku_id)
        # 截取列表中的前五个元素
        pl.ltrim(key, 0, 4)
        # 执行管道
        pl.execute()

        return http.JsonResponse({'code': RETCODE.OK, 'errms': 'OK'})

    def get(self, request):

        user = request.user
        redis_conn = get_redis_connection('history')
        sku_ids = redis_conn.lrange('history_%s' % user.id, 0, -1)
        skus = []

        for sku_id in sku_ids:
            sku_model = SKU.objects.get(id=sku_id)
            skus.append({
                'id': sku_model.id,
                'name': sku_model.name,
                'default_image_url': sku_model.default_image.url,
                'price': sku_model.price
            })

        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'skus': skus})


class FindPasswordView(View):
    """找回密碼"""

    def get(self, request):
        return render(request, 'find_password.html')


class FindPasswordView1(View):
    """找回密碼第一步"""

    def get(self, request, mobile):
        image_code_client = request.GET.get('text')
        image_code_id = request.GET.get('image_code_id')
        user = get_user_by_account(mobile)
        if not user:
            return http.HttpResponseForbidden('用户名或手机号不存在')
        redis_conn = get_redis_connection('verify_code')
        # 2.2 获取redis中的图片验证码
        image_code_server = redis_conn.get('img_%s' % image_code_id)
        # 2.3 删除redis中的图片验证码,让验证码只能用一次
        redis_conn.delete('img_%s' % image_code_id)
        # 2.4 校验图片验证码是否过期
        if image_code_server is None:
            return http.HttpResponseForbidden('图形验证码过期')
        # 2.5 把bytes类型转换成字符串
        image_code_server = image_code_server.decode()
        # 2.6 判断前端和后端的图片验证码是否一致
        if image_code_client.lower() != image_code_server.lower():
            return http.HttpResponseForbidden('请输入正确的短信验证码')
        serializer = Serializer(settings.SECRET_KEY, 3600 * 24)
        user_dict = {'user_id': user.id, 'mobile': user.mobile}
        access_token = serializer.dumps(user_dict).decode()
        mobile = user.mobile[:3] + '*****' + user.mobile[-4:]
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'mobile': mobile, 'access_token': access_token})


class FindPasswordView2(View):

    def get(self, request):
        access_token = request.GET.get('access_token').encode()
        serializer = Serializer(settings.SECRET_KEY, 3600 * 24)
        try:
            user_dict = serializer.loads(access_token)
        except BadData:
            return http.JsonResponse({'error':'数据错误'})
        else:
            mobile = user_dict['mobile']
            sms_code = '%06d' % randint(0, 999999)
            logger.info(sms_code)
            redis_conn = get_redis_connection('verify_code')
            redis_conn.setex('sms_%s' % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
            send_sms_code.delay(mobile, sms_code)
            return http.JsonResponse({'message': 'OK'})


class FindPasswordView3(View):

    def get(self, request, mobile):

        sms_code_client = request.GET.get('sms_code')
        user = get_user_by_account(mobile)
        if not user:
            return http.HttpResponseForbidden('用户名或手机号不存在')
        redis_conn = get_redis_connection('verify_code')
        # 根据对应的标码(sms_mobile),取出数据库中的短信验证码
        sms_code_server = redis_conn.get('sms_%s' % mobile)
        # 取出短信验证码后,将数据库中的验证码马上删掉,不用占用资源,也可以以后重复利用.
        redis_conn.delete(sms_code_server)
        if sms_code_server is None:
            return http.JsonResponse({'message': '短信验证码过期'}, status=403)
        sms_code_server = sms_code_server.decode()
        if sms_code_server != sms_code_client:
            return http.JsonResponse({'message': '短信验证码错误'}, status=403)
        serializer = Serializer(settings.SECRET_KEY, 3600 * 24)
        user_dict = {
            'user_id': user.id,
            'mobile': user.mobile
        }
        access_token = serializer.dumps(user_dict).decode()
        user_id = user.id
        return http.JsonResponse({'message': 'OK', 'access_token': access_token, 'user_id': user_id})


class FindPasswordView4(View):

    def post(self, request, user_id):
        json_dict = json.loads(request.body.decode())
        password = json_dict.get('password')
        password2 = json_dict.get('password2')
        access_token = json_dict.get('access_token').encode()

        if not all([password, password2, access_token]):
            return http.HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return http.HttpResponseForbidden('密码最少8位，最长20位')
        if password != password2:
            return http.HttpResponseForbidden('两次输入的密码不一致')
        serializer = Serializer(settings.SECRET_KEY, 3600 * 24)
        try:
            user_dict = serializer.loads(access_token)
        except BadData:
            return http.JsonResponse({'error':'数据错误'}, status=400)
        if user_dict['user_id'] != int(user_id):
            return http.HttpResponseForbidden('非法请求')
        user = User.objects.get(id=user_id)
        user.set_password(password)
        user.save()
        return http.JsonResponse({'code':RETCODE.OK,'message':'密码设置成功'})


