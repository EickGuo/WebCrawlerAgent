import json
import re
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, Page, ElementHandle
import random

class DoubanMovieScraper:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.movies_data = []
        
    def random_wait(self, min_time=0.5, max_time=1.5):
        """随机等待，模拟人类行为"""
        time.sleep(random.uniform(min_time, max_time))
        
    def check_login_status(self) -> bool:
        """检查是否已登录"""
        print("检查登录状态...")
        self.random_wait()
        
        # 查找登录后的用户信息
        user_elements = self.page.query_selector_all('a[href*="/people/"], .nav-user-account, .bn-more')
        for element in user_elements:
            text = element.text_content().strip()
            if text and ('账号' in text or '我的豆瓣' in text):
                print(f"检测到已登录用户: {text}")
                return True
        
        # 检查是否有登录入口
        login_elements = self.page.query_selector_all('a[href*="/accounts/login"], .lnk-login')
        if login_elements:
            print("未检测到登录状态，需要手动登录")
            return False
            
        print("无法确定登录状态，继续执行...")
        return True
        
    def navigate_with_wait(self, url: str):
        """导航到指定URL并等待加载"""
        print(f"导航到: {url}")
        self.page.goto(url, wait_until="networkidle")
        self.random_wait(1, 2)
        
    def extract_movie_links(self) -> List[str]:
        """提取热门电影链接"""
        print("正在提取热门电影链接...")
        
        # 尝试多种选择器定位电影链接
        selectors = [
            'a[href*="/subject/"]',
            '.movie-list .item a[href*="/subject/"]',
            '.screening-bd a[href*="/subject/"]',
            '.ui-slide-item a[href*="/subject/"]'
        ]
        
        movie_links = []
        seen_urls = set()
        
        for selector in selectors:
            elements = self.page.query_selector_all(selector)
            for element in elements:
                href = element.get_attribute('href')
                if href and '/subject/' in href:
                    full_url = urljoin('https://movie.douban.com', href)
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        movie_links.append(full_url)
            
            if movie_links:
                break
        
        # 如果没有找到，尝试更通用的方法
        if not movie_links:
            all_links = self.page.query_selector_all('a[href*="/subject/"]')
            for link in all_links:
                href = link.get_attribute('href')
                if href:
                    full_url = urljoin('https://movie.douban.com', href)
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        movie_links.append(full_url)
        
        # 去重并限制数量
        unique_links = list(dict.fromkeys(movie_links))
        return unique_links[:10]  # 取前10部电影
        
    def extract_movie_info(self, movie_url: str) -> Optional[Dict[str, Any]]:
        """提取电影详细信息"""
        print(f"正在提取电影信息: {movie_url}")
        self.navigate_with_wait(movie_url)
        
        movie_data = {
            "url": movie_url,
            "title": None,
            "year": None,
            "directors": [],
            "writers": [],
            "actors": [],
            "genres": [],
            "countries": [],
            "languages": [],
            "release_dates": [],
            "duration": None,
            "also_known_as": [],
            "summary": None,
            "rating": None,
            "rating_count": None
        }
        
        try:
            # 提取标题
            title_element = self.page.query_selector('h1 span[property="v:itemreviewed"]')
            if title_element:
                movie_data["title"] = title_element.text_content().strip()
            
            # 提取年份
            year_element = self.page.query_selector('h1 .year')
            if year_element:
                year_text = year_element.text_content().strip()
                year_match = re.search(r'\((\d{4})\)', year_text)
                if year_match:
                    movie_data["year"] = year_match.group(1)
            
            # 提取基本信息
            info_element = self.page.query_selector('#info')
            if info_element:
                info_text = info_element.text_content()
                
                # 提取导演
                director_section = info_element.query_selector('span:has-text("导演")')
                if director_section:
                    director_elements = director_section.query_selector_all('a[rel="v:directedBy"]')
                    movie_data["directors"] = [elem.text_content().strip() for elem in director_elements]
                
                # 提取编剧
                writer_section = info_element.query_selector('span:has-text("编剧")')
                if writer_section:
                    writer_elements = writer_section.query_selector_all('a')
                    movie_data["writers"] = [elem.text_content().strip() for elem in writer_elements]
                
                # 提取主演
                actor_section = info_element.query_selector('span:has-text("主演")')
                if actor_section:
                    actor_elements = actor_section.query_selector_all('a[rel="v:starring"]')
                    movie_data["actors"] = [elem.text_content().strip() for elem in actor_elements]
                
                # 提取类型
                genre_section = info_element.query_selector('span:has-text("类型")')
                if genre_section:
                    genre_elements = genre_section.query_selector_all('a[property="v:genre"]')
                    movie_data["genres"] = [elem.text_content().strip() for elem in genre_elements]
                
                # 提取制片国家/地区
                country_match = re.search(r'制片国家/地区:\s*(.+?)\n', info_text)
                if country_match:
                    countries = country_match.group(1).strip()
                    movie_data["countries"] = [c.strip() for c in countries.split('/') if c.strip()]
                
                # 提取语言
                language_match = re.search(r'语言:\s*(.+?)\n', info_text)
                if language_match:
                    languages = language_match.group(1).strip()
                    movie_data["languages"] = [l.strip() for l in languages.split('/') if l.strip()]
                
                # 提取上映日期
                date_elements = info_element.query_selector_all('a[property="v:initialReleaseDate"]')
                if date_elements:
                    movie_data["release_dates"] = [elem.text_content().strip() for elem in date_elements]
                
                # 提取片长
                duration_element = info_element.query_selector('span[property="v:runtime"]')
                if duration_element:
                    movie_data["duration"] = duration_element.text_content().strip()
                
                # 提取又名
                aka_match = re.search(r'又名:\s*(.+?)(?:\n|$)', info_text)
                if aka_match:
                    aka_text = aka_match.group(1).strip()
                    movie_data["also_known_as"] = [a.strip() for a in aka_text.split('/') if a.strip()]
            
            # 提取剧情简介
            summary_element = self.page.query_selector('#link-report-intra span[property="v:summary"]')
            if summary_element:
                summary_text = summary_element.text_content().strip()
                # 清理多余的空白字符
                summary_text = re.sub(r'\s+', ' ', summary_text)
                movie_data["summary"] = summary_text
            
            # 提取评分信息
            rating_element = self.page.query_selector('strong[property="v:average"]')
            if rating_element:
                movie_data["rating"] = rating_element.text_content().strip()
            
            rating_count_element = self.page.query_selector('span[property="v:votes"]')
            if rating_count_element:
                movie_data["rating_count"] = rating_count_element.text_content().strip()
            
            # 如果评分为空，设置为"暂无评分"
            if not movie_data["rating"]:
                movie_data["rating"] = "暂无评分"
                movie_data["rating_count"] = "0"
            
            return movie_data
            
        except Exception as e:
            print(f"提取电影信息时出错: {e}")
            return None
        
    def run(self):
        """主执行函数"""
        with sync_playwright() as playwright:
            self.playwright = playwright
            self.browser = playwright.chromium.launch(headless=False)
            self.page = self.browser.new_page()
            
            try:
                # 步骤1：打开豆瓣首页并检查登录状态
                print("步骤1：打开豆瓣首页...")
                self.navigate_with_wait('https://www.douban.com/')
                
                if not self.check_login_status():
                    print("\n" + "="*60)
                    print("检测到未登录状态！")
                    print("请手动在浏览器中登录豆瓣账号")
                    print("登录完成后，请在控制台输入 'continue' 并按回车键继续")
                    print("="*60 + "\n")
                    
                    while True:
                        user_input = input("输入 'continue' 继续: ").strip().lower()
                        if user_input == 'continue':
                            # 重新检查登录状态
                            self.page.reload()
                            self.random_wait(2, 3)
                            if self.check_login_status():
                                print("登录验证成功，继续执行...")
                                break
                            else:
                                print("仍然未检测到登录状态，请确认已登录")
                        else:
                            print("无效输入，请输入 'continue'")
                
                # 步骤2：导航到豆瓣电影首页
                print("\n步骤2：导航到豆瓣电影首页...")
                self.navigate_with_wait('https://movie.douban.com/')
                
                # 验证是否成功进入电影首页
                title = self.page.title()
                if "豆瓣电影" not in title:
                    print(f"警告：可能未正确进入电影首页，当前标题: {title}")
                
                # 步骤3：定位热门电影列表
                print("\n步骤3：定位热门电影列表...")
                movie_links = self.extract_movie_links()
                
                if not movie_links:
                    print("未找到电影链接，尝试滚动页面...")
                    self.page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    self.random_wait()
                    movie_links = self.extract_movie_links()
                
                if not movie_links:
                    print("错误：无法找到电影链接")
                    return
                
                print(f"找到 {len(movie_links)} 部电影")
                for i, link in enumerate(movie_links, 1):
                    print(f"{i}. {link}")
                
                # 步骤4：遍历电影详情页并提取信息
                print("\n步骤4：提取电影详细信息...")
                for i, movie_url in enumerate(movie_links, 1):
                    print(f"\n正在处理第 {i}/{len(movie_links)} 部电影...")
                    
                    movie_info = self.extract_movie_info(movie_url)
                    if movie_info:
                        self.movies_data.append(movie_info)
                        print(f"成功提取: {movie_info.get('title', '未知标题')}")
                    else:
                        print(f"跳过: {movie_url}")
                    
                    # 在处理完一部电影后等待一下
                    if i < len(movie_links):
                        self.random_wait()
                
                # 步骤5：整理为JSON格式并返回
                print("\n步骤5：整理数据为JSON格式...")
                
                if not self.movies_data:
                    print("未提取到任何电影数据")
                    return
                
                # 转换为JSON
                json_output = json.dumps(self.movies_data, ensure_ascii=False, indent=2)
                
                print("\n" + "="*60)
                print("提取完成！共提取到 {} 部电影信息".format(len(self.movies_data)))
                print("="*60 + "\n")
                
                # 输出JSON数据
                print(json_output)
                
                # 可选：保存到文件
                with open('douban_movies.json', 'w', encoding='utf-8') as f:
                    f.write(json_output)
                print(f"\n数据已保存到: douban_movies.json")
                
            except Exception as e:
                print(f"执行过程中出错: {e}")
                import traceback
                traceback.print_exc()
                
            finally:
                # 保持浏览器打开，让用户查看结果
                print("\n按回车键关闭浏览器...")
                input()
                self.browser.close()

if __name__ == "__main__":
    scraper = DoubanMovieScraper()
    scraper.run()