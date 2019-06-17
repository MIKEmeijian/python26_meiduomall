from django.core.cache import cache
from django.shortcuts import render
from django.views import View
from django import http

from meiduo_mall.utils.response_code import RETCODE
from .models import Area




class AreasView(View):
    """提供省市区数据查询"""
    def get(self, request):
    # 获取查询参数area_id
        area_id = request.GET.get('area_id')
    # 判断area_id有没有值,如果没有值说明是要查询所有省
        if area_id is None:
        # 查询所有省数据
        # 当要查询所有省数据时,先尝试性的去redis中查询,如果没有再去mysql中查询
            province_list = cache.get('province_list')
            if province_list is None:
                province_qs = Area.objects.filter(parent= None)
                # 把查询集中的模型对象转换成字典格式
                province_list = []  # 用来装每一个省的字典数据
                for province_model in province_qs:
                    province_list.append({
                        'id': province_model.id,
                        'name': province_model.name
                    })
                cache.set('province_list', province_list, 3600)
            # 响应
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'province_list': province_list})

        else:
            """查询指定省下面的所有市或指定市下面的所有区数据"""
            # 获取指定省或市的缓存数据
            sub_data = cache.get('sub_area_' + area_id)
            if sub_data is None:
                # 把当前area_id指定的单个省或市查询出来
                try:
                    parent_model = Area.objects.get(id=area_id)
                except Area.DoesNotExist:
                    return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': 'area_id不存在'})

                # 再通过单个省或市查询出它的下级所有行政区
                # parent_model.parent  # 直接外键代表拿到一的那方模型
                subs_qs = parent_model.subs.all()  # 通过一查询多时,需要在后面多写一个all
                # 定义一个列表变量用来包装所有下级行政区的字典数据
                sub_list = []
                # 遍历行政区查询集,把每个模型转换成字典
                for sub_model in subs_qs:
                   sub_list.append({
                       'id': sub_model.id,
                       'name': sub_model.name
                   })
                # 包装好响应数据
                sub_data = {
                    'id':parent_model.id,
                    'name': parent_model.name,
                    'subs': sub_list
                }
                # 把当前数据进行缓存
                cache.set('sub_area_' + area_id, sub_data, 3600)

            # 响应
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'sub_data': sub_data})
