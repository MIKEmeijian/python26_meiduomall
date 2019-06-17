import pickle, base64
from django_redis import get_redis_connection


def merge_cart_cookie_to_redis(request, response):

    cart_str = request.COOKIES.get('carts')
    user = request.user
    if cart_str is None:
        return
    cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))

    redis_conn = get_redis_connection('carts')
    for sku_id, sku_dict in cart_dict.items():
        redis_conn.hset('carts_%s' % user.id, sku_id, sku_dict['count'])
        if sku_dict['selected']:
            redis_conn.sadd('selected_%s' % user.id, sku_id)
        else:
            redis_conn.srem('selected_%s' % user.id, sku_id)

    response.delete_cookie('carts')