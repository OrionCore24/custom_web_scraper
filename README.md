# Custom Web Scraper

A Python-based web scraping project that explores automated data collection from different websites using Selenium. This project focuses on extracting structured information from NBA player statistics and Alibaba product search results.

## 📌 Project Overview

The **Custom Web Scraper** project was developed to practice web scraping, browser automation, and data collection using Python. It covers two different use cases: collecting basketball statistics and gathering product information from an e-commerce platform.

The project demonstrates how web scraping can help transform information displayed on websites into structured data for further processing and analysis.

## 🎯 Objectives

- Practice web scraping using Python and Selenium.
- Automate browser interactions with dynamic websites.
- Collect structured data from different website layouts.
- Explore data collection for sports analytics and e-commerce research.
- Build practical skills in data processing and preparation.

## 🌐 Target Websites

### 1. NBA Player Statistics

**Website:** [NBA.com/stats](https://www.nba.com/stats/players/traditional?PerMode=Totals&Season=2025-26)

Collect player statistics from the NBA's Traditional Player Statistics page for the 2025–26 season.

**Potential data fields include:**
- Player name
- Team
- Games played
- Points
- Rebounds
- Assists
- Other traditional basketball statistics available on the page

The exact fields collected depend on the scraper implementation and the data available on the website.

### 2. Alibaba Product Search

**Website:** [Alibaba Product Search — Scissors](https://www.alibaba.com/trade/search?fsb=y&IndexArea=product_en&CatId=&SearchText=scissors&viewtype=&tab=&has4Tab=true)

Collect product information from Alibaba's search results for the keyword `scissors`.

**Potential data fields include:**
- Product name
- Product price
- Minimum order quantity
- Supplier information
- Other product details available in the search results

The exact fields collected depend on the scraper implementation and the information displayed by Alibaba.

## 🛠️ Technologies Used

- **Python** — Main programming language.
- **Selenium** — Browser automation and interaction with dynamic web pages.
- **Pandas** — Data manipulation and tabular data processing, where used.

## 📂 Project Structure

```text
custom_web_scraper/
│
├── nba_scraper.py
├── alibaba_scraper.py
├── README.md
└── .gitignore
```

*Note: This is a suggested structure. Adjust the filenames to match the actual files in your project.*

## ⚙️ Installation and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR-USERNAME/custom-web-scraper.git
```

### 2. Navigate to the Project Directory

```bash
cd custom-web-scraper
```

### 3. Create a Virtual Environment

```bash
python -m venv scraper
```

Activate the environment on Windows:

```powershell
.\scraper\Scripts\Activate.ps1
```

### 4. Install Dependencies

If the project contains a `requirements.txt` file:

```bash
pip install -r requirements.txt
```

Otherwise, install the packages required by your scripts.

### 5. Run the Scraper

For the NBA scraper:

```bash
python nba_scraper.py
```

For the Alibaba scraper, replace the example filename with the actual script filename:

```bash
python alibaba_scraper.py
```

## 📊 Output

The scraper is intended to collect website information in a structured format that can be used for further processing and analysis.

Depending on the implementation, the collected data may be saved as CSV files or processed using Pandas.

## ⚠️ Notes and Limitations

- Website layouts and HTML elements may change, requiring updates to the scraping code.
- Dynamic content may require additional loading time or browser interactions.
- Scraping results depend on the information available when the scraper runs.
- Some websites may apply rate limits or other access restrictions.
- Use responsible scraping practices and respect each website's terms of service and applicable data-use policies.

## 📚 Learning Outcomes

Through this project, I aim to improve my understanding of:

- Web scraping and browser automation
- Extracting structured data from websites
- Handling dynamic web content
- Data collection and preprocessing
- Preparing data for exploratory analysis

## 👤 Author

**Your Name**

Aspiring Data Analyst | Python & Data Enthusiast

---

This project is part of my learning journey in Python programming, web scraping, and data analytics.
