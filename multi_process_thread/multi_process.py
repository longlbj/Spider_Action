# coding:utf-8
import urllib2
from collections import deque
import json
from lxml import etree
import httplib
import hashlib
from pybloomfilter import BloomFilter
import thread
import threading
import time

from dbmanager import CrawlDatabaseManager
from mysql.connector import errorcode
import mysql.connector


'''
 整个代码的思想就是：逐级的将url并将其md5加密和bloomFilter并存储，并且下载其html页面存储到本地
'''


request_headers = {
    'host': "www.mafengwo.cn",
    'connection': "keep-alive",
    'cache-control': "no-cache",
    'upgrade-insecure-requests': "1",
    'user-agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.95 Safari/537.36",
    'accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    'accept-language': "zh-CN,en-US;q=0.8,en;q=0.6"
}


##下载网页内容
def get_page_content(cur_url,index,depth):
    print 'downloading %s at level %d' % (cur_url, depth)
    try:
        req = urllib2.Request(cur_url, headers=request_headers)  ##模仿浏览器行为向服务器发出请求
        response = urllib2.urlopen(req)
        html_page = response.read()  ## 下载html网页
        filename = cur_url[7:].replace('/', '_')  ##将网址中w开始后的'/'用'_'替代，将url映射成对应的文件名
        fo = open("%s%s.html" % (dir_name, filename), 'wb+')  ##二进制模式加读写模式打开文件
        fo.write(html_page)  ## 将html写入到fo中
        fo.close()
        dbmanager.finishUrl(index)
    except urllib2.HTTPError, Arguments:
        print Arguments
        return
    except httplib.BadStatusLine, Arguments:
        print Arguments
        return
    except IOError, Arguments:
        print Arguments
        return
    except Exception, Arguments:
        print Arguments
        return


    '''
    使用lxml前注意事项：先确保html经过了utf-8解码，即code = html.decode('utf-8', 'ignore')，否则会出现解析出错情况。
    因为中文被编码成utf-8之后变成 '/u2541'　之类的形式，lxml一遇到　“/”就会认为其标签结束。
    '''
    html = etree.HTML(html_page.lower().decode('utf-8'))
    hrefs = html.xpath(u"//a")  ## 找到所有网址链接

    for href in hrefs:
        try:
            if 'href' in href.attrib:
                val = href.attrib['href']  ##获取 href属性对应的value
                if val.find('javascript:') != -1:
                    continue
                if val.startswith('http://') is False:  ##说明此时是相对网址
                    if val.startswith('/'):
                        val = 'http://www.mafengwo.cn' + val  ##使其变成绝对路径
                    else:
                        continue
                if val[-1] == '/':
                    val = val[0:-1]  ##去除最后一个'/'字符
                #crawler.enqueueUrl(val)  ##将其加入到child_queue，并且使其经过md5加密和bloom filter
                dbmanager.enqueueUrl(val,depth+1)
        except ValueError:
            continue

max_num_thread=5
dbmanager=CrawlDatabaseManager(max_num_thread)
dir_name='dir_process/'
dbmanager.enqueueUrl("http://www.mafengwo.cn",0)

start_time = time.time()

## 如果是第一个抓取页面的话，在主线程用同步(阻塞) 的模式下载，后续的页面会通过创建子线程的方式异步抓取
is_root_page = True  ##种子网址，第一层的网址
threads = []

CRAWL_DELAY = 0.6
while True:
    #url = crawler.dequeueUrl()  ##当前层队列(cur_deque)出队列返回url
    curtask=dbmanager.dequeueUrl()
    if curtask is None:  ## 如果url为None，则说明队列为空
        for t in threads:
            t.join()  ##停止所有线程
        break


    ## 在线程池中寻找空的线程来进行爬取
    if is_root_page is True:
        ## 如果是种子网址
        get_page_content(curtask['url'],curtask['index'],curtask['depth'])
        is_root_page = False
    else:
        while True:
            ## 去掉已经完成爬取任务的线程
            for t in threads:
                if not t.is_alive():
                    threads.remove(t)
            if len(threads) > max_num_thread:
                time.sleep(CRAWL_DELAY)
                continue
            try:
                t = threading.Thread(target=get_page_content, name=None, args=(curtask['url'],curtask['index'],curtask['depth'],))
                threads.append(t)
                ## 设置daemon,这样在接受到ctrl-c 时，可以中断主线程
                t.setDaemon(True)
                t.start()
                time.sleep(CRAWL_DELAY)
                break
            except Exception:
                print 'Error:unable to start thread'
