from django.conf.urls import url
from django.contrib import admin
from . import views

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^register/$', views.RegisterView.as_view(), name='register'),
    url(r'^usernames/(?P<username>[a-zA-Z0-9_-]{5,20})/count/$', views.UsernameCountView.as_view()),
    url(r'^mobiles/(?P<mobile>1[3-9]\d{9})/count/$', views.MobileCountView.as_view()),
    url(r'^login/$', views.LoginView.as_view()),
    url(r'^logout/$', views.LogoutView.as_view()),
    url(r'^info/$', views.UserInfoView.as_view(), name='info'),
    url(r'^emails/$', views.EmailView.as_view()),
    url(r'^emails/verification/$', views.VerifyEmailView.as_view()),
    url(r'^addresses/$', views.AddressView.as_view(), name='address'),
    url(r'^addresses/create/$', views.CreateAddressView.as_view()),
    url(r'^addresses/(?P<address_id>\d+)/$', views.UpdateDestroyAddressView.as_view()),
    url(r'^addresses/(?P<address_id>\d+)/default/$', views.DefaultAddressView.as_view()),
    url(r'^addresses/(?P<address_id>\d+)/title/$', views.UpdateTitleAddressView.as_view()),
    url(r'^password/$', views.ChangePasswordView.as_view()),
    url(r'^browse_histories/$', views.UserBrowseHistory.as_view()),
    # 找回密碼
    url(r'^find_password/$', views.FindPasswordView.as_view()),
    # 找回密碼 第1步
    url(r'^accounts/(?P<mobile>1[3-9]\d{9})/sms/token/$', views.FindPasswordView1.as_view()),
    # 找回密碼 第2步
    url(r'^sms_codes/', views.FindPasswordView2.as_view()),
    # 找回密碼 第3步
    url(r'^accounts/(?P<mobile>1[3-9]\d{9})/password/token/$', views.FindPasswordView3.as_view()),
    # 找回密碼 第4步
    url(r'^users/(?P<user_id>\d+)/password/$', views.FindPasswordView4.as_view()),
]
