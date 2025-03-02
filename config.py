# 配置文件：存储目标公司和爬取网站信息
import datetime

# 目标公司列表
TARGET_COMPANIES = []  # 清空默认列表

# 招投标信息网站配置
TENDER_WEBSITES = [
    {
        "name": "中国政府采购网",
        "url": "http://www.ccgp.gov.cn/",
        "search_api": "http://search.ccgp.gov.cn/bxsearch",
        "params": {
            "searchtype": "1",  # 1表示招标公告
            "page_index": "{page}",
            "bidSort": "0",
            "buyerName": "",
            "projectId": "",
            "pinMu": "0",
            "bidType": "0",
            "dbselect": "bidx",
            "kw": "{keyword}",  # 公司名称关键词
            "start_time": "{start_time}",  # 开始时间 格式：yyyy:MM:dd
            "end_time": "{end_time}",  # 结束时间 格式：yyyy:MM:dd
            "timeType": "6",  # 时间类型
            "displayZone": "0",
        },
        "result_xpath": {
            "items": "//div[@class='vT-srch-result-list-bid']//li",
            "title": ".//a/text()",
            "url": ".//a/@href",
            "publish_date": ".//span/text()",
            "content": ".//p/text()"
        }
    },
    # 可添加其他招投标网站配置
]

# 抓取时间范围（默认为近3个月）
today = datetime.datetime.now()
three_months_ago = today - datetime.timedelta(days=90)

DEFAULT_START_DATE = three_months_ago.strftime("%Y:%m:%d")
DEFAULT_END_DATE = today.strftime("%Y:%m:%d")

# 输出文件路径
OUTPUT_DIR = "outputs" 