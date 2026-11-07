'''
Function:
    Implementation of IQiyiVideoClient
Author:
    Zhenchao Jin
WeChat Official Account (微信公众号):
    Charles的皮卡丘
'''
import os
import re
import time
import copy
import string
import random
import hashlib
from .base import BaseVideoClient
from urllib.parse import urlencode, quote
from ..utils.domains import IQIYI_SUFFIXES
from ..utils import legalizestring, useparseheaderscookies, resp2json, touchdir, yieldtimerelatedtitle, safeextractfromdict, taskprogress, VideoInfo


'''IQiyiVideoClient'''
class IQiyiVideoClient(BaseVideoClient):
    source = 'IQiyiVideoClient'
    class VideoTypes:
        MOVIE = "MOV"; TV = "TV"; CARTOON = "Cartoon"; SPORTS = "Sports"; ENTMT = "Ent"; GAME = "Game"; DOCU = "Docu"; VARIETY = "Variety"; MUSIC = "Music"; NEWS = "News"; FINANCE = "Finance"
        FASHION = "Fashion"; TRAVEL = "Travel"; EDUCATION = "Edu"; TECH = "Tech"; AUTO = "Auto"; HOUSE = "House"; LIFE = "Life"; FUN = "Fun"; BABY = "Baby"; CHILD = "Child"; ART = "Art"
    IQIYI_DEFN_MAP_I2S = {800: 'uhd', 600: 'fhd', 500: 'shd', 300: 'hd', 200: 'sd'}
    IQIYI_DEFN_MAP_S2I = {'dolby': 800, 'suhd': 800, 'hdr10': 800, 'uhd': 800, 'fhd': 600, 'shd': 500, 'hd': 300, 'sd': 200}
    TVID_PAT_RE = re.compile(r"\"tvid\":\s*(?P<tvid>\d+)", re.MULTILINE | re.DOTALL | re.IGNORECASE)
    PLAYER_INIT_URL = 'https://mesh.if.iqiyi.com/player/lw/lwplay/accelerator.js?apiVer=3'
    VIDEO_COVER_PREFIX = 'https://pcw-api.iqiyi.com/video/video/baseinfo'
    VIDEO_CONFIG_URL = 'https://cache.video.iqiyi.com/dash'
    APP_VERSION = '13.062.22175'
    def __init__(self, **kwargs):
        super(IQiyiVideoClient, self).__init__(**kwargs)
        self.default_parse_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36', 'Accept-Encoding': 'gzip, deflate, br', 'Accept': '*/*', 'Connection': 'keep-alive'}
        self.default_download_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'}
        self.default_headers = self.default_parse_headers
        self._initsession()
    '''_calcvf'''
    def _calcvf(self, url):
        ovappend_func = lambda e: e + ''.join(chr(((70*t + 677*i + 21*n + 87*t*i*n + 59) % 30) + (48 if ((70*t + 677*i + 21*n + 87*t*i*n + 59) % 30) < 9 else 88)) for t in range(4) for i in range(2) for n in range(4))
        path_n_query = re.sub(r"^(https?://)?cache\.video\.iqiyi\.com", "", url, flags=re.IGNORECASE)
        return hashlib.md5(ovappend_func(path_n_query).encode('utf-8')).hexdigest()
    '''_authkey'''
    def _authkey(self, tm, tvid):
        giveaway = hashlib.md5("".encode('utf-8')).hexdigest()
        return hashlib.md5((giveaway + str(tm) + str(tvid)).encode('utf-8')).hexdigest()
    '''_generatedeviceid'''
    def _generatedeviceid(self):
        random.seed()
        random_str = "".join(random.choices(string.printable, k=128))
        device_id = hashlib.md5(random_str.encode('utf-8')).hexdigest()
        return device_id
    '''_getvideocoverinfo'''
    def _getvideocoverinfo(self, url, device_id, request_overrides: dict = None):
        request_overrides = request_overrides or {}
        try:
            resp = self.get(IQiyiVideoClient.PLAYER_INIT_URL, headers={'referer': url}, **request_overrides)
            resp.raise_for_status()
            resp.encoding = 'utf-8'
            tvid = IQiyiVideoClient.TVID_PAT_RE.search(resp.text).group('tvid')
            # The public metadata endpoint identifies videos by their TV ID.
            resp = self.get(f'{IQiyiVideoClient.VIDEO_COVER_PREFIX}/{tvid}', **request_overrides)
            resp.raise_for_status()
            resp.encoding = 'utf-8'
            raw_data = resp2json(resp=resp)
            if raw_data.get('code') != 'A00000':
                return None
            data = raw_data['data']
            if str(data.get('tvId')) != tvid:
                return None
            title = data.get('subtitle') or data.get('name')
            if not title:
                return None
            image_url = data.get('albumImageUrl') or data.get('imageUrl')
            if image_url:
                image_url = re.sub(r'^http://', 'https://', image_url)
            return {
                'image_url': image_url, 'url': url, 'referrer': url,
                'title': data.get('albumName') or data.get('name') or title,
                'year': str(data.get('period') or data.get('publishDate') or '')[:4],
                'cover_id': data.get('albumId') or data['tvId'],
                'type': IQiyiVideoClient.VideoTypes.MOVIE if str(data.get('channelId')) == '1' else IQiyiVideoClient.VideoTypes.TV,
                'episode_all': data.get('videoCount') or 1,
                'normal_ids': [{'V': data['tvId'], 'E': data.get('order') or 1, 'defns': {}, 'title': title, 'url': url, 'referrer': url}],
            }
        except Exception:
            return None
    '''_updatevideodwnldinfo'''
    def _updatevideodwnldinfo(self, vi, device_id, request_overrides: dict = None):
        tm, request_overrides = int(time.time() * 1000), request_overrides or {}
        params = {'tvid': vi['V'], 'bid': IQiyiVideoClient.IQIYI_DEFN_MAP_S2I['uhd'], 'vid': '', 'src': '01010031010000000000', 'vt': 0, 'rs': 1, 'uid': '', 'ori': 'pcw', 'ps': 1, 'k_uid': device_id, 'pt': 0, 'd': 0, 's': '', 'lid': 0, 'cf': 0, 'ct': 0, 'authKey': self._authkey(tm, vi['V']), 'k_tag': 1, 'dfp': '', 'locale': 'zh_cn', 'pck': '', 'k_err_retries': 0, 'up': '', 'qd_v': 'a1', 'tm': tm, 'k_ft1': '706436220846084', 'k_ft4': '1162321298202628', 'k_ft5': '150994945', 'k_ft7': '4', 'fr_300': '120_120_120_120_120_120', 'fr_500': '120_120_120_120_120_120', 'fr_600': '120_120_120_120_120_120', 'fr_800': '120_120_120_120_120_120', 'fr_1020': '120_120_120_120_120_120', 'bop': quote('{"version":"10.0","dfp":"","b_ft1":28}'), 'sr': 1, 'ost': 0, 'ut': 0}
        params['vf'] = self._calcvf('/dash?' + urlencode(params))
        try:
            (resp := self.get(IQiyiVideoClient.VIDEO_CONFIG_URL + '?' + urlencode(params), **request_overrides)).raise_for_status(); resp.encoding = 'utf-8'
            vd = [vd for vd in sorted(resp2json(resp=resp)['data']['program']['video'], key=lambda x: x['bid'], reverse=True) if vd.get('m3u8') and vd['ff'] != 'dash'][0]
            ts_urls = [ts for ts in vd['m3u8'].split('\n') if ts and not ts.startswith('#')]
            std_defn = IQiyiVideoClient.IQIYI_DEFN_MAP_I2S[vd['bid']]
            vi["defns"].setdefault(std_defn, []).append(dict(ext=vd['ff'], urls=ts_urls))
            vi['highest_defns_original'] = vd['m3u8']
        except Exception: pass
    '''parsefromurl'''
    @useparseheaderscookies
    def parsefromurl(self, url: str, request_overrides: dict = None) -> list[VideoInfo]:
        # prepare
        if not self.belongto(url=url): return []
        request_overrides, video_info, null_backup_title, device_id, video_infos = request_overrides or {}, VideoInfo(source=self.source, enable_nm3u8dlre=True), yieldtimerelatedtitle(self.source), self._generatedeviceid(), []
        # try parse
        try:
            raw_data = self._getvideocoverinfo(url, device_id=device_id, request_overrides=request_overrides)
            with taskprogress(description='Possible Multiple Videos Detected >>> Parsing One by One', total=len((extracted_normal_ids := safeextractfromdict(raw_data, ['normal_ids'], [])))) as progress:
                for extracted_normal_id in extracted_normal_ids:
                    self._updatevideodwnldinfo(extracted_normal_id, device_id=device_id, request_overrides=request_overrides)
                    touchdir(os.path.dirname((download_url := os.path.join(self.work_dir, self.source, f'{extracted_normal_id["V"]}.m3u8'))))
                    with open(download_url, 'w') as fp: fp.write(extracted_normal_id['highest_defns_original'])
                    (video_info_page := copy.deepcopy(video_info)).update(raw_data=raw_data, download_url=download_url)
                    video_title = legalizestring(extracted_normal_id['title'] or null_backup_title, replace_null_string=null_backup_title).removesuffix('.')
                    video_title = f'EP{len(video_infos)+1}-{video_title}' if len(raw_data['normal_ids']) > 1 else video_title
                    video_info_page.update(dict(title=video_title, save_path=os.path.join(self.work_dir, self.source, f'{video_title}.m3u8'), ext='mp4', identifier=extracted_normal_id["V"], cover_url=raw_data.get('image_url'))); video_infos.append(video_info_page); progress.advance(1)
        except Exception as err:
            video_info.update(dict(err_msg=(err_msg := f'{self.source}.parsefromurl >>> {url} (Error: {err})'))); video_infos.append(video_info)
            self.logger_handle.error(err_msg, disable_print=self.disable_print)
        # return
        return video_infos
    '''belongto'''
    @staticmethod
    def belongto(url: str, valid_domains: list[str] | set[str] = None):
        valid_domains = set(valid_domains or []) | IQIYI_SUFFIXES
        return BaseVideoClient.belongto(url, valid_domains)
