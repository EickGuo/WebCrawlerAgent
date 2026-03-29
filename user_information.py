def user_information():
    return {
        "url": "https://www.xiaohongshu.com/explore",                            # Your target URL for web crawling.
        "user_request": '',                   # Your request for web crawling and information extraction. Be as specific as possible about the data you want and the format you want it in.
        "max_exploration_steps": 10,          # Maximum number of exploration steps allowed for dynamic crawling. Adjust based on the complexity of the website and your needs.
        "max_detail_samples": 3,              # Maximum number of detail page samples to collect for pattern recognition. Increase if the website has high variability in page structures.
        "max_debug_rounds": 2,                # Maximum number of debug rounds allowed. Adjust based on the complexity of the website and your needs.
    }