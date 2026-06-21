from src.util import is_url, safe_url
from src.util.m3u import load_online_m3u

if __name__ == "__main__":
    url = "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E7%A6%8F%E5%BB%BA%E8%81%94%E9%80%9A%E5%8D%95%E6%92%AD%E6%BA%90.m3u"
    new_url = safe_url(url)
    if is_url(new_url):
