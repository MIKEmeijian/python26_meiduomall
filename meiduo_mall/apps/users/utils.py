import re
from django.contrib.auth.backends import ModelBackend
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer, BadData
from .models import User
from django.conf import settings


def get_user_by_account(account):
    try:
        if re.match(r'^1[3-9]\d{9}$', account):
            user = User.objects.get(mobile=account)

        else:
            user = User.objects.get(username=account)

    except User.DoesNotExist:
        return None
    return user


class UsernameMobileAuthBackend(ModelBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):
        # 1.获取user(mobile, username)
        user = get_user_by_account(username)
        # 2.校验密码是否正确
        if user and user.check_password(password) and user.is_active:
            # 3.返回
            return user


def generate_email_verify_url(user):

    serializer = Serializer(settings.SECRET_KEY, 3600 * 24)
    data = {'user_id': user.id, 'email': user.email}
    token = serializer.dumps(data).decode()
    verify_url = settings.EMAIL_VERIFY_URL + '?token=' + token
    return verify_url

def check_verify_token(token):

    serializer = Serializer(settings.SECRET_KEY, 3600 * 24)
    try:
        data = serializer.loads(token)
    except BadData:
        return None
    else:
        user_id = data.get('user_id')
        email = data.get('email')
        try:
            user = User.objects.get(id=user_id, email=email)
        except User.DoesNotExist:
            return None
        else:
            return user