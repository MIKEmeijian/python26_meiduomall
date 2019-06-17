from django.core.files.storage import Storage


class FastDFSStorage(Storage):
    """自定义文件存储类"""

    def _open(self, name, mode='rb'):
        """当需要打开文件时会来调用此方法
        name: 要打开的文件名
        mode: 文件打开模式
        """
        pass

    def _save(self, name, content):
        """
        当使用fastDFS进行上传图片时就会来调用此方法
        :param name: 要上传的图片文件名
        :param content: 要上传文件的二进行制数据
        :return: file_id
        """
        # with open(name, 'rb') as f:
        #     content = f.read()
        pass

    def url(self, name):
        """
        当使用ImageFiled类型字段调用url属性时就会来调用此方法拼接图片文件的绝对路径
        :param name: file_id
        :return: 图片文件绝对路径
        """
        return 'http://192.168.153.132:8888/' + name
