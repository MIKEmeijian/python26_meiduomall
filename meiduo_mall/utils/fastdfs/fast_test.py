from fdfs_client.client import Fdfs_client

# 创建fdfs客户端
client = Fdfs_client('./client.conf')
# 使用客户端上传图片
ret = client.upload_by_filename('/home/python/Desktop/01.jpeg')
print(ret)

'''
ret={'Group name': 'group1', 
'Remote file_id': 'group1/M00/00/00/wKiZhFzuO5GAS7EsAAC4j90Tziw29.jpeg', 
'Status': 'Upload successed.', 'Local file name': '/home/python/Desktop/01.jpeg', 
'Uploaded size': '46.00KB', 'Storage IP': '192.168.153.132'}
'''