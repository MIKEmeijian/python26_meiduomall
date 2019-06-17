from celery_tasks.sms.yuntongxun.sms import CCP
from celery_tasks.main import celery_app


@celery_app.task(name='send_sms_code')
def send_sms_code(mobile, sms_code):
    CCP().send_template_sms(mobile, [sms_code, 5], 1)
