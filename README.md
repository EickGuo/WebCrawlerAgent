# Web Crawler Agent

An automated web crawling agent designed specifically for batch data extraction.

## Project Overview

This project implements an intelligent web crawler agent that automates the process of extracting data from websites. For detailed project logic and architecture, please refer to `project_logic.md` (Chinese version).

## Prerequisites

- Python 3.8 or higher
- Playwright browser automation library

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Playwright Browsers

After installing the Python dependencies, run the following command to install the required browsers:

```bash
playwright install
```

## Configuration

### 1. User information

Before running the project, configure the user-specific settings in `user_information.py`:

- Modify or complete the required fields as needed
- Add any custom configurations specific to your use case

### 2. Environment Variables

Create a `.env` file in the project root directory with the following format:

```.env
# API configuration
API_KEY=your_api_key_here
API_BASE_URL=llm_api_url
API_MODEL=your_chosen_llm_model

# Scraping information (highly possibly removed or updated in other format later)
USER_AGENT=""
```

## Usage

After completing the configuration:

- Ensure all dependencies are installed

- Fill in `user_information.py` with your target data

- Configure the `.env` file with your API credentials and other necessary information

- Run the main script:

```bash
python main.py
```

## Project Structure

```text
├── main.py                 # Entry point
├── user_information.py     # User-specific configuration
├── llm.py                  
├── nodes.py
├── prompts.py
├── schemas.py
├── state.py
├── tools.py
├── validators.py
├── project_logic.md        # Project logic documentation (Chinese)
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (create this file)
└── README.md               # This file
```

