from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from goods.models import GoodsCategory, GoodsChannel
from .models import ContentCategory, Content


class IndexView(View):

    def get(self, request):

        categories = {}
        good_channels_qs = GoodsChannel.objects.order_by('group_id', 'sequence')

        for channel in good_channels_qs:
            group_id = channel.group_id

            if group_id not in categories:
                categories[group_id] = {'channels': [], 'sub_cats': []}

            cat1 = channel.category
            cat1.url = channel.url
            categories[group_id]['channels'].append(cat1)

            cat2_qs = cat1.subs.all()
            for cat2 in cat2_qs:
                cat3_qs = cat2.subs.all()
                cat2.sub_cats = cat3_qs
                categories[group_id]['sub_cats'].append(cat2)

        contents = {}
        content_category_qs = ContentCategory.objects.all()
        for cat in content_category_qs:
            contents[cat.key] = cat.content_set.filter(status=True).order_by('sequence')

        context = {
            'categories': categories,
            'contents': contents
        }
        print(context)

        return render(request, 'index.html', context)
