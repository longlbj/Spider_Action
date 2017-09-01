#coding:utf-8
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


'''
 整个代码的思想就是：逐级的将url并将其md5加密和bloomFilter并存储，并且下载其html页面存储到本地
'''
class CrawlBSF:
    request_headers={ ## 使用代理来模仿浏览器行为
        'host': "www.mafengwo.cn",
        'connection': "keep-alive",
        'cache-control': "no-cache",
        'upgrade-insecure-requests': "1",
        'user-agent': "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.101 Safari/537.36",
        'accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        'accept-language': "zh-CN,en-US;q=0.8,en;q=0.6"
    }

    cur_level=0 ##当前处于第几级的爬取
    max_level=3 ## 最大爬取级别
    dir_name='iterate/' ##文件夹根目录
    iter_width=30
    downloaded_urls=[] ## 已经下载完成的url

    du_md5_file_name=dir_name+'download.txt' ##经过md5加密后的文件名
    du_url_file_name=dir_name+'urls.txt' ##下载存储原始的url


    '''
    用来哈希压缩，并且可以用来防止碰撞
    class pybloomfilter.BloomFilter(capacity : int, error_rate : float[, filename=None : string ][,
    perm=0755 ])
    并不实际检查容量,如果需要比较低的error_rate,则需要设置更大的容量
    '''
    bloom_downloaded_urls=BloomFilter(1024*1024*16,0.01)## 用来保存已经下载其网页的且经过md5哈希的url
    bloom_url_queue=BloomFilter(1024*1024*16,0.01)## 用来插入经过md5哈希的并且还没有下载其网页的url，并且每次插入到child_queue时，
    #都会检查是否在bloom_url_queue里面，用来记录是否已经爬取过

    cur_queue=deque() ##建立当前队列对象，存储当前层的(级别)的url
    child_queue=deque() ##子队列 ，用来存储当前层url的html中的网址链接url


    def __init__(self,url):
        self.root_url=url
        self.cur_queue.append(url) ##将当前的url入队
        self.du_file=open(self.du_url_file_name,'a+') ##写入模式打开文件
        try:
            self.dumd5_file=open(self.du_md5_file_name,'r') ## 读取模式打开文件，里面存储的是经md5哈希加密的url
            self.downloaded_urls=self.dumd5_file.readlines() ## 读取文件每一行
            self.dumd5_file.close()
            for urlmd5 in self.downloaded_urls: ##遍历经过md5加密后的每一个url
                self.bloom_downloaded_urls.add(urlmd5[:-2]) ##对其url进行bloomfilter
        except IOError:
            print 'File not Found'
        finally:
            self.dumd5_file=open(self.du_md5_file_name,'a+') ##写入模式打开文件


    def enqueueUrl(self,url):
        ## 将当前url(cur_url)中html中的网址链接url插入到子队列(child_queue)中
        ## 将url进行md5哈希加密，然后在加入child_queue队列，然后在进行blood_filter
        ## hashlib.md5(url).hexdigest():url经过md5加密并且返回十六进制的密文，并且这些密文以字符串形式返回
        if url not in self.bloom_url_queue and hashlib.md5(url).hexdigest() not in crawler.bloom_downloaded_urls:
            self.child_queue.append(url)
            self.bloom_url_queue.add(url)

    def dequeueUrl(self):
        ## 出队列，返回url
        try:
            ## 删除并返回当前队列最左边的元素，这是个原子操作，两个线程不会同时pop同一个url
            url=self.cur_queue.popleft()
            return url
        except IndexError:
            return None

    def close(self):
        self.dumd5_file.close()
        self.du_file.close()

num_downloaded_pages=0


##下载网页内容
def get_page_content(cur_url):
    global num_downloaded_pages
    print 'downloading %s at level %d' %(cur_url,crawler.cur_level)
    try:
        req=urllib2.Request(cur_url,headers=crawler.request_headers) ##模仿浏览器行为向服务器发出请求
        response=urllib2.urlopen(req)
        html_page=response.read() ## 下载html网页
        filename=cur_url[7:].replace('/','_') ##将网址中w开始后的'/'用'_'替代，将url映射成对应的文件名
        fo=open("%s%s.html" %(crawler.dir_name,filename),'wb+') ##二进制模式加读写模式打开文件
        fo.write(html_page) ## 将html写入到fo中
        fo.close()
    except urllib2.HTTPError,Arguments:
        print Arguments
        return
    except httplib.BadStatusLine,Arguments:
        print Arguments
        return
    except IOError,Arguments:
        print Arguments
        return
    except Exception,Arguments:
        print Arguments
        return

    dumd5=hashlib.md5(cur_url).hexdigest() ## 将当前url进行md5加密哈希，返回十六进制的字符串
    crawler.downloaded_urls.append(dumd5)  ##　将url对应的十六进制字符串加入到downloaded_urls
    crawler.dumd5_file.write(dumd5+'\r\n') ## 也将url对应的十六进制字符串写入dumd5_file
    crawler.du_file.write(cur_url+'\r\n')
    crawler.bloom_downloaded_urls.add(dumd5) ##将经过ma5哈希加密的url再进行bloom filter
    num_downloaded_pages+=1 ##下载网页数加1

    '''
    使用lxml前注意事项：先确保html经过了utf-8解码，即code = html.decode('utf-8', 'ignore')，否则会出现解析出错情况。
    因为中文被编码成utf-8之后变成 '/u2541'　之类的形式，lxml一遇到　“/”就会认为其标签结束。
    '''
    html=etree.HTML(html_page.lower().decode('utf-8'))
    hrefs=html.xpath(u"//a") ## 找到所有网址链接

    for href in hrefs:
        try:
            if 'href' in href.attrib:
                val=href.attrib['href'] ##获取 href属性对应的value
                if val.find('javascript:')!=-1:
                    continue
                if val.startswith('http://') is False:##说明此时是相对网址
                    if val.startswith('/'):
                        val='http://www.mafengwo.cn'+val ##使其变成绝对路径
                    else:
                        continue
                if val[-1]=='/':
                    val=val[0:-1] ##去除最后一个'/'字符
                crawler.enqueueUrl(val) ##将其加入到child_queue，并且使其经过md5加密和bloom filter
        except ValueError:
            continue

crawler=CrawlBSF('http://www.mafengwo.cn')
start_time=time.time()

## 如果是第一个抓取页面的话，在主线程用同步(阻塞) 的模式下载，后续的页面会通过创建子线程的方式异步抓取
is_root_page=True ##种子网址，第一层的网址
threads=[]
max_threads=10

CRAWL_DELAY=0.6
while True:
    url=crawler.dequeueUrl() ##当前层队列(cur_deque)出队列返回url
    if url is None: ## 如果url为None，则说明队列为空
        crawler.cur_level+=1 ## 队列为空则爬取级别加1
        for t in threads:
            t.join() ##停止所有线程
        if crawler.cur_level==crawler.max_level:
            break ##达到最大爬取级别则停止
        if len(crawler.child_queue)==0:
            break
        crawler.cur_queue=crawler.child_queue ##将子队列赋值给当前队列
        crawler.child_queue=deque() ## 重新创建子队列对象
        continue

    ## 在线程池中寻找空的线程来进行爬取
    if is_root_page is True:
        ## 如果是种子网址
        get_page_content(url)
        is_root_page=False
    else:
        while True:
            ## 去掉已经完成爬取任务的线程
            for t in threads:
                if not t.is_alive():
                    threads.remove(t)
            if len(threads)>max_threads:
                time.sleep(CRAWL_DELAY)
                continue
            try:
                t=threading.Thread(target=get_page_content,name=None,args=(url,))
                threads.append(t)
                ## 设置daemon,这样在接受到ctrl-c 时，可以中断主线程
                t.setDaemon(True)
                t.start()
                time.sleep(CRAWL_DELAY)
                break
            except Exception:
                print 'Error:unable to start thread'

print '%d pages downloaded,time cost %0.2f seconds' %(num_downloaded_pages,time.time()-start_time)
