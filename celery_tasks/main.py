import os
from celery import Celery


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "meiduo_mall.settings.dev")
# 1.创建celery实例对象  创建celery客户端
celery_app = Celery('meiduo')

# 2.加载配置信息  指定谁来当中间人,指定仓库的位置
celery_app.config_from_object('celery_tasks.config')

# 3.自定注册人物(当前只处理哪些任务）
celery_app.autodiscover_tasks(['celery_tasks.sms', 'celery_tasks.email'])
