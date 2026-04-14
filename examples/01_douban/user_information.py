def user_information():
    return {
        "url": "https://www.douban.com/",                            # Your target URL for web crawling.
        "user_request": '帮我提取热门电影下的详细电影信息，整理成json格式返回给我。',                   # Your request for web crawling and information extraction. Be as specific as possible about the data you want and the format you want it in.
        "max_exploration_steps": 10,          # Maximum number of exploration steps allowed for dynamic crawling. Adjust based on the complexity of the website and your needs.
        "max_detail_samples": 3,              # Maximum number of detail-oriented reference snapshots to keep during exploration.
        "max_resume_attempts": 3,             # Maximum resume attempts when exploration is blocked by login / captcha / verification.
    }
