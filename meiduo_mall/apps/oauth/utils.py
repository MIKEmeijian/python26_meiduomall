from itsdangerous import TimedJSONWebSignatureSerializer as Serializer, BadData
from django.conf import settings


def generate_openid_signature(openid):
    # 1.创建加密对象
    serializer = Serializer(settings.SECRET_KEY, 600)
    # 2.包装数据为字典类型
    data = {'openid': openid}
    # 3.调用dumps方法进行加密,加密后返回的是bytes类型
    openid_sign = serializer.dumps(data)  # 得到一个字节类型数据
    return openid_sign.decode()  # 把字节类型数据解码变成字符串


def check_openid_signature(openid):

    serializer = Serializer(settings.SECRET_KEY, 600)
    try:
        data = serializer.loads(openid)
    except BadData:
        return None
    return data.get('openid')


def generate_uid_signature(access_token):
    # 1.创建加密对象
    serializer = Serializer(settings.SECRET_KEY, 600)
    # 2.包装数据为字典类型
    data = {'access_token': access_token}
    # 3.调用dumps方法进行加密,加密后返回的是bytes类型
    openid_sign = serializer.dumps(data)  # 得到一个字节类型数据
    return openid_sign.decode()  # 把字节类型数据解码变成字符串


def check_uid_signature(access_token):

    serializer = Serializer(settings.SECRET_KEY, 600)
    try:
        data = serializer.loads(access_token)
    except BadData:
        return None
    return data.get('access_token')