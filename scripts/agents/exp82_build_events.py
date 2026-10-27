"""Exp 82 step 0 -- build the event table from official documents (no price is read here).

Two stages:
  export  : read the scratch extraction files (release lists already parsed for payment dates, ASX Appendix 3A.1
            fields, issuer PDFs) and write compact source lists (date, payment date, URL) to
            docs/agents/results/exp82_sources/.  Web content is treated as data only (regex extraction).
  build   : combine the source lists with the DRIP regimes below (each regime = a range of payment dates whose
            source/discount is stated in the cited official document) -> docs/agents/results/Exp-82_events.csv.

Status vocabulary (statut_doc):
  explicite              the cited document states the treatment for this payment (or announces it "until further
                         notice" and a later document confirms it was still in force);
  jusqu_a_avis_contraire covered only by an "until further notice" statement, no later confirmation found;
  retroactif             documented by a later "previously / most recently" statement;
  non_documente          payment date found but treatment not documented -> excluded from all statistics.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "agents" / "results" / "exp82_sources"
OUT = ROOT / "docs" / "agents" / "results" / "Exp-82_events.csv"

ISSUERS = {
    "RY.TO": ("Banque Royale du Canada", "banque"), "TD.TO": ("Banque Toronto-Dominion", "banque"),
    "BMO.TO": ("Banque de Montreal", "banque"), "BNS.TO": ("Banque Scotia", "banque"),
    "CM.TO": ("CIBC", "banque"), "MFC.TO": ("Manuvie", "assureur"), "SLF.TO": ("Financiere Sun Life", "assureur"),
    "ENB.TO": ("Enbridge", "pipeline"), "TRP.TO": ("TC Energy (TransCanada)", "pipeline"),
    "PPL.TO": ("Pembina Pipeline", "pipeline"), "BCE.TO": ("BCE", "telecom"),
    "T-A.TO": ("TELUS (actions sans droit de vote, T.A)", "telecom"), "T.TO": ("TELUS (ordinaires)", "telecom"),
    "NAB.AX": ("National Australia Bank", "banque"), "ANZ.AX": ("ANZ", "banque"),
    "WBC.AX": ("Westpac", "banque"), "CBA.AX": ("Commonwealth Bank", "banque"),
}

U = {  # regime documents (official)
    "RY_AR2009": "https://www.sec.gov/Archives/edgar/data/1000275/000119312509247131/dex2.htm",
    "RY_2009_12": "https://www.newswire.ca/news-releases/royal-bank-of-canada-declares-dividends-539045121.html",
    "RY_2010_12": "https://www.newswire.ca/news-releases/royal-bank-of-canada-declares-dividends-547095312.html",
    "RY_2011_Q2": "https://www.sec.gov/Archives/edgar/data/1000275/000119312511152412/dex992.htm",
    "RY_2012_05": "https://www.newswire.ca/news-releases/royal-bank-of-canada-declares-dividends-510273851.html",
    "RY_2022_11": "https://www.newswire.ca/news-releases/royal-bank-of-canada-declares-dividends-896928990.html",
    "RY_2024_02": "https://www.newswire.ca/news-releases/royal-bank-of-canada-declares-dividends-804036632.html",
    "TD_2002_11": "https://www.sec.gov/Archives/edgar/data/947263/000104746902004970/a2094955z6-k.htm",
    "TD_2003_11": "https://www.sec.gov/Archives/edgar/data/947263/000104746903038673/a2123414z6-k.htm",
    "TD_2004_02": "https://www.sec.gov/Archives/edgar/data/947263/000104746904005698/a2129215z6-k.htm",
    "TD_2004_09": "https://www.sec.gov/Archives/edgar/data/947263/000104746904027975/a2143094z6-k.htm",
    "TD_2006_08": "https://www.sec.gov/Archives/edgar/data/947263/000127956906000947/tdbank6k.htm",
    "TD_2008_05": "https://www.sec.gov/Archives/edgar/data/947263/000119312508125522/d424b2.htm",
    "TD_2013_02": "https://www.sec.gov/Archives/edgar/data/947263/000119312513083987/d494378d424b2.htm",
    "TD_2020_05": "https://www.newswire.ca/news-releases/td-bank-group-reports-second-quarter-2020-results-881572464.html",
    "TD_2020_08": "https://www.newswire.ca/news-releases/td-bank-group-reports-third-quarter-2020-results-817079988.html",
    "TD_2022_05": "https://www.newswire.ca/news-releases/td-bank-group-reports-second-quarter-2022-results-808033270.html",
    "TD_2023_05": "https://www.newswire.ca/news-releases/td-bank-group-reports-second-quarter-2023-results-800577454.html",
    "TD_2025_02": "https://www.newswire.ca/news-releases/td-bank-group-reports-first-quarter-2025-results-888887665.html",
    "TD_CIRC": "https://www.td.com/content/dam/tdcom/canada/about-td/pdf/dividendes/td-investor-drip-eng.pdf",
    "BMO_2009_01": "https://newsroom.bmo.com/2009-01-06-Bank-of-Montreal-Offers-2-Discount-on-the-Reinvestment-of-Dividends-in-Newly-Issued-Common-Shares-Under-its-Shareholder-Dividend-Reinvestment-and-Share-Purchase-Plan",
    "BMO_2010_08": "https://newsroom.bmo.com/2010-08-24-BMO-Financial-Group-Declares-Dividend",
    "BMO_2011_12": "https://newsroom.bmo.com/2011-12-06-BMO-Financial-Group-Declares-Dividend-and-Introduces-a-2-Per-Cent-Discount-on-its-Dividend-Reinvestment-Plan",
    "BMO_2012_08": "https://newsroom.bmo.com/2012-08-28-BMO-Financial-Group-Increases-Dividend",
    "BMO_2013_05": "https://newsroom.bmo.com/2013-05-29-BMO-Financial-Group-Declares-Dividend",
    "BMO_2014_02": "https://newsroom.bmo.com/2014-02-25-BMO-Financial-Group-Declares-Dividend",
    "BMO_2014_05": "https://newsroom.bmo.com/2014-05-28-BMO-Financial-Group-Declares-Dividends",
    "BMO_2014_08": "https://newsroom.bmo.com/2014-08-26-BMO-Financial-Group-Declares-Dividends",
    "BMO_2014_12": "https://newsroom.bmo.com/2014-12-02-BMO-Financial-Group-Increases-Common-Share-Dividend",
    "BMO_2016_10": "https://newsroom.bmo.com/2016-10-17-BMO-Introduces-a-Two-Per-Cent-Discount-for-Shares-Issued-Under-its-Dividend-Reinvestment-Plan",
    "BMO_2017_02": "https://newsroom.bmo.com/2017-02-28-BMO-Financial-Group-Declares-Dividends",
    "BMO_2017_05": "https://newsroom.bmo.com/2017-05-24-BMO-Financial-Group-Increases-Common-Share-Dividend",
    "BMO_2020_04": "https://newsroom.bmo.com/2020-04-08-BMO-Introduces-a-Two-Per-Cent-Discount-for-Shares-Issued-Under-its-Dividend-Reinvestment-Plan",
    "BMO_2020_08": "https://newsroom.bmo.com/2020-08-25-BMO-Financial-Group-Declares-Dividends",
    "BMO_2022_01": "https://newsroom.bmo.com/2022-01-10-BMO-Introduces-a-Two-Per-Cent-Discount-for-Shares-Issued-Under-its-Dividend-Reinvestment-Plan",
    "BMO_2024_02": "https://newsroom.bmo.com/2024-02-27-BMO-Financial-Group-Declares-Dividends",
    "BMO_PROSP": "https://www.sec.gov/Archives/edgar/data/927971/000090956709000014/o42709e424b3.htm",
    "BNS_AR2009": "https://www.sec.gov/Archives/edgar/data/9631/000095012309070811/o58134cexv99w1.htm",
    "BNS_AR2010": "https://www.sec.gov/Archives/edgar/data/9631/000095012310110657/o66745arexv99w1.htm",
    "BNS_2017_02": "https://www.newswire.ca/news-releases/scotiabank-announces-dividend-on-outstanding-shares-614949413.html",
    "BNS_2023_02": "https://www.newswire.ca/news-releases/scotiabank-announces-dividend-on-outstanding-shares-830321385.html",
    "BNS_2024_08": "https://www.newswire.ca/news-releases/scotiabank-announces-dividend-on-outstanding-shares-836958597.html",
    "BNS_2024_12": "https://www.newswire.ca/news-releases/scotiabank-announces-dividend-on-outstanding-shares-861486714.html",
    "CM_2009_05": "https://cibc.mediaroom.com/2009-05-28-CIBC-announces-amendments-to-its-shareholder-investment-plan,1",
    "CM_2011_02": "https://cibc.mediaroom.com/2011-02-24-CIBC-declares-dividends,1",
    "CM_2012_03": "https://cibc.mediaroom.com/2012-03-08-CIBC-declares-dividends,1",
    "CM_2012_12": "https://cibc.mediaroom.com/2012-12-06-CIBC-declares-dividends,1",
    "CM_2016_08": "https://cibc.mediaroom.com/2016-08-25-CIBC-declares-dividends-and-announces-elections-under-its-shareholder-investment-plan",
    "CM_2018_02": "https://cibc.mediaroom.com/2018-02-22-CIBC-Increases-Dividends",
    "CM_2022_12": "https://cibc.mediaroom.com/2022-12-09-CIBC-announces-a-two-per-cent-discount-for-shares-issued-under-its-Shareholder-Investment-Plan",
    "CM_2024_05": "https://cibc.mediaroom.com/2024-05-30-CIBC-Declares-Dividends-for-the-Quarter-Ending-July-31,-2024-and-announces-a-change-to-its-Shareholder-Investment-Plan",
    "CM_2024_12": "https://cibc.mediaroom.com/2024-12-05-CIBC-Increases-Dividends-for-the-Quarter-Ending-January-31,-2025",
    "MFC_2009_08": "https://www.sec.gov/Archives/edgar/data/1086888/000108688809000043/ex99-3.htm",
    "MFC_2011_02": "https://www.sec.gov/Archives/edgar/data/1086888/000108688811000004/exhibit99-1.htm",
    "MFC_2014_08": "https://www.newswire.ca/news-releases/manulife-financial-corporation-increases-dividend-515214111.html",
    "MFC_2014_11": "https://www.newswire.ca/news-releases/manulife-financial-corporation-declares-dividends-516388971.html",
    "MFC_2020_02": "https://www.newswire.ca/news-releases/manulife-increases-common-shareholders-dividend-by-12--843837887.html",
    "SLF_2009_08": "https://www.sec.gov/Archives/edgar/data/1097362/000095012309031074/o56412aexv99w1.htm",
    "SLF_2013_11": "https://www.sec.gov/Archives/edgar/data/1097362/000119312513432612/d612654dex992.htm",
    "SLF_AR2016": "https://www.sec.gov/Archives/edgar/data/1097362/000119312517099023/d329360dex995.htm",
    "ENB_2008_01": "https://www.sec.gov/Archives/edgar/data/895728/000113031908000089/o39165e6vk.htm",
    "ENB_SUSP": "https://www.sec.gov/Archives/edgar/data/895728/000110465923098253/tm2325426d1_424b5.htm",
    "TRP_2007_01": "https://www.sec.gov/Archives/edgar/data/1232384/000110465907005818/a07-2962_1ex99d1.htm",
    "TRP_2009_02": "https://www.sec.gov/Archives/edgar/data/1232384/000009907009000002/exhibit991.htm",
    "TRP_2011_04": "https://www.sec.gov/Archives/edgar/data/1232384/000126329111000017/exhibit991tccq104292011.htm",
    "TRP_2016_07": "https://www.sec.gov/Archives/edgar/data/1232384/000123238416000136/exhibit991tcc2016q2dividen.htm",
    "TRP_2019_11": "https://www.sec.gov/Archives/edgar/data/1232384/000123238419000078/exhibit991tceq42019dividen.htm",
    "TRP_2022_07": "https://www.sec.gov/Archives/edgar/data/1232384/000123238422000071/trp-06302022xfinstmts.htm",
    "TRP_2023_07": "https://www.sec.gov/Archives/edgar/data/1232384/000123238423000067/a07272023-tcenergydeclar.htm",
    "PPL_2010_03": "https://www.newswire.ca/news-releases/pembina-announces-march-2010-distribution-and-suspension-of-premiumdistribution-distribution-reinvestment-and-optional-unit-purchase-plan-539612312.html",
    "PPL_AIF2012": "https://www.sec.gov/Archives/edgar/data/1546066/000127956913000230/v336501_ex99-1.htm",
    "PPL_PLAN": "https://www.sec.gov/Archives/edgar/data/1546066/000127956913000444/v340465_ex4-1.htm",
    "PPL_2017_03": "https://www.newswire.ca/news-releases/pembina-pipeline-corporation-declares-march-2017-common-share-dividend-and-suspension-of-the-dividend-reinvestment-plan-615616734.html",
    "BCE_HIST": "https://www.bce.ca/cs-assets/2025-april-drp-historical-purchase-price-1975-now.pdf-blt560a7ed1ed451c85",
    "BCE_PAGE": "https://www.bce.ca/investors/shareholder-info",
    "BCE_CIRC": "https://www.bce.ca/cs-assets/2024-drp-offering-circular.pdf-bltfcbd93b5929fc95d",
    "T_2004_11": "https://www.sec.gov/Archives/edgar/data/868675/",
    "T_2009_11": "https://www.newswire.ca/news-releases/telus-amends-dividend-reinvestment-program-538897591.html",
    "T_2010_11": "https://www.newswire.ca/news-releases/telus-reports-third-quarter-2010-results-546193982.html",
    "T_2012_11": "https://www.newswire.ca/news-releases/telus-reports-third-quarter-2012-results-511128791.html",
    "T_2025_12": "https://www.newswire.ca/news-releases/telus-provides-three-year-free-cash-flow-growth-target-886437730.html",
    "T_2026_02": "https://www.newswire.ca/news-releases/telus-amends-dividend-reinvestment-program-800040603.html",
    "T_2026_07": "https://www.newswire.ca/news-releases/telus-reports-second-quarter-2026-financial-and-operational-results-and-resets-quarterly-dividend-to-support-deleveraging-and-fuel-long-term-growth-824663865.html",
}

# (ticker, first_pay, last_pay, source_achat, rabais_pct, statut, url_key, citation courte)
REGIMES = [
    ("RY.TO", "2009-05-22", "2009-11-24", "tresor", 3, "explicite", "RY_AR2009", "Effective May 1, 2009, first dividend payable May 22, 2009: DRIP at a 3% discount (5 trading days)"),
    ("RY.TO", "2010-02-24", "2010-11-24", "marche", 0, "explicite", "RY_2009_12", "decided to purchase shares on the open market with no applicable discount; Q1-2011 report: open market"),
    ("RY.TO", "2011-02-24", "2012-05-24", "tresor", 0, "explicite", "RY_2010_12", "issue shares from treasury with no applicable discount until further notice"),
    ("RY.TO", "2012-08-24", "2022-11-24", "marche", 0, "explicite", "RY_2012_05", "purchase shares on the open market with no applicable discounts; confirmed 2022-11-30 'most recently ... secondary market'"),
    ("RY.TO", "2023-02-24", "2024-02-23", "tresor", 2, "explicite", "RY_2022_11", "For the February 24, 2023 dividend ... treasury at a 2% discount"),
    ("RY.TO", "2024-05-24", "2026-11-24", "marche", 0, "explicite", "RY_2024_02", "For the May 24, 2024 dividend ... secondary market with no discount"),
    ("TD.TO", "2003-01-31", "2003-10-31", "tresor", 2.5, "explicite", "TD_2002_11", "elected to issue shares from treasury at a 2 1/2 % discount"),
    ("TD.TO", "2004-01-31", "2004-01-31", "tresor", 1, "explicite", "TD_2003_11", "changed from 2 1/2 % to 1%, effective for the dividend for the quarter ending January 31, 2004"),
    ("TD.TO", "2004-04-30", "2004-07-31", "tresor", 0, "explicite", "TD_2004_02", "no discount, effective for the quarter ending April 30, 2004"),
    ("TD.TO", "2004-10-31", "2006-07-31", "tresor", 1, "explicite", "TD_2004_09", "1% discount for the dividend payable October 31, 2004; continued each quarter to May 2006"),
    ("TD.TO", "2006-10-31", "2008-04-30", "tresor", 0, "explicite", "TD_2006_08", "no discount, effective for the quarter ending October 31, 2006"),
    ("TD.TO", "2008-07-31", "2013-01-31", "tresor", 1, "explicite", "TD_2008_05", "reintroduce a 1% discount; first dividend payable July 31, 2008; 'continue at 1%' each quarter to Dec 2012"),
    ("TD.TO", "2013-04-30", "2020-04-30", "tresor", 0, "explicite", "TD_2013_02", "continue to issue from treasury, but with no discount"),
    ("TD.TO", "2020-07-31", "2020-07-31", "tresor", 2, "explicite", "TD_2020_05", "will apply a 2% discount (dividend declared May 28, 2020)"),
    ("TD.TO", "2020-10-31", "2022-04-30", "tresor", 0, "explicite", "TD_2020_08", "continue to issue from treasury, but with no discount"),
    ("TD.TO", "2022-07-31", "2023-04-30", "tresor", 2, "explicite", "TD_2022_05", "apply a 2% discount (dividend declared May 26, 2022); confirmed each quarter to April 30, 2023"),
    ("TD.TO", "2023-07-31", "2025-01-31", "tresor", 0, "explicite", "TD_2023_05", "continue to issue from treasury, but with no discount"),
    ("TD.TO", "2025-04-30", "2026-10-31", "marche", 0, "explicite", "TD_2025_02", "purchase the additional shares in the open market and therefore no discount"),
    ("BMO.TO", "2009-02-26", "2010-08-27", "tresor", 2, "explicite", "BMO_2009_01", "issue shares from treasury at a two per cent discount (Q1 2009 dividend onward)"),
    ("BMO.TO", "2010-11-26", "2011-11-28", "tresor", 0, "explicite", "BMO_2010_08", "issued from treasury without discount"),
    ("BMO.TO", "2012-02-28", "2012-08-28", "tresor", 2, "explicite", "BMO_2011_12", "issue shares from treasury at a 2 per cent discount"),
    ("BMO.TO", "2012-11-28", "2013-05-29", "tresor", 0, "explicite", "BMO_2012_08", "For the dividend payable on November 28, 2012 ... from treasury without a discount"),
    ("BMO.TO", "2013-08-27", "2014-02-26", "marche", 0, "explicite", "BMO_2013_05", "purchased on the open market beginning with the dividend payable on August 27, 2013"),
    ("BMO.TO", "2014-05-26", "2014-05-29", "tresor", 0, "explicite", "BMO_2014_02", "issued by the Bank from treasury without discount"),
    ("BMO.TO", "2014-08-26", "2014-08-28", "tresor", 2, "explicite", "BMO_2014_05", "two percent discount; confirmed 2014-08-26 'A two per cent discount applied ... last quarter'"),
    ("BMO.TO", "2014-11-26", "2014-11-28", "tresor", 0, "explicite", "BMO_2014_08", "issued from treasury without a discount"),
    ("BMO.TO", "2015-02-26", "2016-08-30", "marche", 0, "explicite", "BMO_2014_12", "purchased on the open market without a discount until further notice; superseded 2016-10-17"),
    ("BMO.TO", "2016-11-28", "2017-02-28", "tresor", 2, "explicite", "BMO_2016_10", "two per cent discount effective with the Q4 2016 dividend; Q1 2017 confirmed"),
    ("BMO.TO", "2017-05-26", "2017-05-30", "tresor", 0, "explicite", "BMO_2017_02", "issued from treasury without a discount (Q2 2017)"),
    ("BMO.TO", "2017-08-28", "2020-02-28", "marche", 0, "explicite", "BMO_2017_05", "purchased on the open market (each quarter)"),
    ("BMO.TO", "2020-05-25", "2020-08-28", "tresor", 2, "explicite", "BMO_2020_04", "two percent discount commencing with the Q2 2020 dividend; Q3 2020 confirmed"),
    ("BMO.TO", "2020-11-26", "2021-11-29", "marche", 0, "explicite", "BMO_2020_08", "purchased on the open market"),
    ("BMO.TO", "2022-02-28", "2024-02-28", "tresor", 2, "explicite", "BMO_2022_01", "two per cent discount commencing with the Q1 2022 dividend; confirmed to the Q1 2024 dividend"),
    ("BMO.TO", "2024-05-28", "2026-11-30", "marche", 0, "explicite", "BMO_2024_02", "purchased on the open market without a discount"),
    ("BNS.TO", "2010-01-27", "2010-01-27", "tresor", 2, "explicite", "BNS_AR2009", "Annual report (Dec 15, 2009): plan ... at a 2% discount to the average market price"),
    ("BNS.TO", "2011-01-27", "2011-01-27", "tresor", 2, "explicite", "BNS_AR2010", "Annual report (Dec 3, 2010): ... at a 2% discount to the average market price"),
    ("BNS.TO", "2017-04-26", "2023-01-27", "marche", 0, "explicite", "BNS_2017_02", "discontinued the issuance of common shares from treasury; purchases in the secondary market"),
    ("BNS.TO", "2023-04-26", "2024-10-29", "tresor", 2, "explicite", "BNS_2023_02", "issue Common Shares from treasury, with a 2% discount (until October 31, 2024)"),
    ("BNS.TO", "2025-01-28", "2026-10-29", "marche", 0, "explicite", "BNS_2024_12", "suspended the discount ... discontinued issuance from treasury"),
    ("CM.TO", "2009-04-28", "2009-04-28", "marche", 0, "retroactif", "CM_2009_05", "Previously, shares were purchased on the secondary market with no discount"),
    ("CM.TO", "2009-07-28", "2011-01-28", "tresor", 3, "explicite", "CM_2009_05", "issue shares from treasury at a 3% discount, effective with the dividend payable July 28, 2009"),
    ("CM.TO", "2011-04-28", "2012-04-27", "tresor", 2, "explicite", "CM_2011_02", "commencing with the dividend to be paid on April 28, 2011 ... 2% discount (previously 3%)"),
    ("CM.TO", "2012-07-27", "2012-10-29", "tresor", 0, "explicite", "CM_2012_03", "commencing with the dividend to be paid on July 27, 2012 ... without discount"),
    ("CM.TO", "2013-01-28", "2016-07-28", "marche", 0, "explicite", "CM_2012_12", "purchase shares in the secondary market starting with the dividend payable on January 28, 2013; confirmed 2016-08-25"),
    ("CM.TO", "2016-10-28", "2018-01-29", "tresor", 2, "explicite", "CM_2016_08", "issue from treasury starting with the dividend payable October 28, 2016 ... 2% discount; confirmed 2018-02-22"),
    ("CM.TO", "2018-04-27", "2022-10-28", "tresor", 0, "explicite", "CM_2018_02", "without discount (from April 27, 2018); 2022-12-09: 'previously ... treasury with no discount'"),
    ("CM.TO", "2023-01-27", "2024-04-29", "tresor", 2, "explicite", "CM_2022_12", "2% discount from the January 27, 2023 dividend; 2024-05-30: 'previously ... 2% discount'"),
    ("CM.TO", "2024-07-29", "2024-10-28", "tresor", 0, "explicite", "CM_2024_05", "For the July 29, 2024 dividend ... treasury without a discount"),
    ("CM.TO", "2025-01-28", "2026-10-28", "marche", 0, "explicite", "CM_2024_12", "For the January 28, 2025 dividend ... purchased from the secondary market"),
    ("MFC.TO", "2009-09-21", "2010-12-20", "tresor", 3, "explicite", "MFC_2009_08", "September 21, 2009 dividend ... three (3) percent discount; repeated each quarter to Dec 2010"),
    ("MFC.TO", "2011-03-21", "2014-09-19", "tresor", 2, "explicite", "MFC_2011_02", "two (2%) per cent discount (decrease from 3%); repeated each quarter to the September 19, 2014 dividend"),
    ("MFC.TO", "2014-12-19", "2018-09-19", "marche", 0, "explicite", "MFC_2014_11", "purchased on the open market; no applicable discounts (each quarter)"),
    ("MFC.TO", "2018-12-19", "2019-12-19", "tresor", 2, "explicite", "MFC_2020_02", "from December 19, 2018 to December 19, 2019 ... issued from treasury ... 2% discount"),
    ("MFC.TO", "2020-03-19", "2026-12-21", "marche", 0, "explicite", "MFC_2020_02", "purchase common shares on the open market commencing with the March 19, 2020 dividend (repeated each quarter)"),
    ("SLF.TO", "2009-06-30", "2013-06-28", "tresor", 2, "explicite", "SLF_2009_08", "issued common shares from treasury at a discount of 2% (quarterly notes 2009-2013)"),
    ("SLF.TO", "2013-09-30", "2015-12-31", "tresor", 0, "explicite", "SLF_2013_11", "third quarter of 2013 ... issued with no discount; until further notice ... treasury, but with no discount"),
    ("SLF.TO", "2016-03-31", "2019-12-31", "marche", 0, "explicite", "SLF_AR2016", "commencing with the dividends paid on March 31, 2016, common shares were acquired ... on the open market"),
    ("ENB.TO", "2008-03-01", "2018-09-01", "tresor", 2, "explicite", "ENB_2008_01", "two per cent discount ... effective with dividends payable on March 1, 2008 (repeated in each MD&A to 2018)"),
    ("ENB.TO", "2018-12-01", "2026-12-01", "suspendu", 0, "explicite", "ENB_SUSP", "dividend reinvestment and share purchase plan ... suspended effective November 2, 2018"),
    ("TRP.TO", "2007-01-31", "2007-01-31", "marche", 0, "retroactif", "TRP_2007_01", "Previously, shares purchased through the DRP have been purchased ... on the open market"),
    ("TRP.TO", "2007-04-30", "2008-10-31", "tresor", 2, "explicite", "TRP_2007_01", "issue common shares from treasury at a two per cent discount, commencing with the dividend payable on April 30, 2007"),
    ("TRP.TO", "2009-01-30", "2011-04-29", "tresor", 3, "explicite", "TRP_2009_02", "increase in the discount ... from two to three per cent for the dividend payable on January 30, 2009"),
    ("TRP.TO", "2011-07-29", "2016-07-29", "marche", 0, "explicite", "TRP_2011_04", "commencing with the dividends declared April 28, 2011 ... acquired on the TSX at 100 per cent"),
    ("TRP.TO", "2016-10-31", "2019-10-31", "tresor", 2, "explicite", "TRP_2016_07", "commencing with the dividends declared today ... treasury at a two per cent discount"),
    ("TRP.TO", "2020-01-31", "2022-07-29", "marche", 0, "explicite", "TRP_2019_11", "commencing with the dividends declared October 31, 2019 ... no longer ... from treasury at a discount"),
    ("TRP.TO", "2022-10-31", "2023-07-31", "tresor", 2, "explicite", "TRP_2022_07", "reinstated issuance ... at a two per cent discount commencing with the dividends declared on July 27, 2022"),
    ("TRP.TO", "2023-10-31", "2026-10-30", "marche", 0, "jusqu_a_avis_contraire", "TRP_2023_07", "commencing with the dividends declared on July 27, 2023 ... acquired on the TSX at 100 per cent"),
    ("PPL.TO", "2010-05-14", "2012-01-16", "suspendu", 0, "explicite", "PPL_2010_03", "suspending its ... DRIP effective April 25, 2010"),
    ("PPL.TO", "2012-02-15", "2017-04-17", "tresor", 5, "explicite", "PPL_AIF2012", "reinstated the DRIP effective January 25, 2012 ... 95 per cent of the Average Market Price"),
    ("PPL.TO", "2017-05-15", "2022-12-30", "suspendu", 0, "explicite", "PPL_2017_03", "suspended, until further notice, its Premium Dividend and DRIP, effective April 25, 2017"),
    ("BCE.TO", "2000-01-15", "2024-10-15", "non_precise", 0, "explicite", "BCE_HIST", "Jan 1988 - cancellation of the 5% discount; Jan 2025 - DRP modified in Nov 2024 to offer a 2% discount"),
    ("BCE.TO", "2025-01-15", "2025-04-15", "tresor", 2, "explicite", "BCE_HIST", "2% discount on treasury shares (Jan 2025); removed effective July 15, 2025"),
    ("BCE.TO", "2025-07-15", "2025-07-15", "marche", 0, "explicite", "BCE_PAGE", "no longer issued from treasury at a 2% discount ... effective with the dividend payable on July 15, 2025"),
    ("T-A.TO", "2010-01-04", "2011-01-04", "tresor", 3, "explicite", "T_2009_11", "non-voting shares from treasury at a three per cent discount (first: January 4, 2010; last: January 4, 2011)"),
    ("T-A.TO", "2011-04-01", "2013-01-02", "marche", 0, "explicite", "T_2010_11", "open market purchases at full price from March 1, 2011; restated Nov 2012"),
    ("T.TO", "2026-01-02", "2026-01-02", "tresor", 2, "explicite", "T_2025_12", "current Discounted DRIP of 2 per cent (stepped down from 2026)"),
    ("T.TO", "2026-04-01", "2026-07-02", "tresor", 1.75, "explicite", "T_2026_02", "1.75 per cent for dividends declared in February and May 2026"),
    ("T.TO", "2026-10-01", "2026-10-01", "non_precise", 0, "explicite", "T_2026_07", "the DRIP discount will be removed effective October 1, 2026"),
]

WINDOW_DEF = {
    "RY.TO": "P-5..P-1 (rapport RBC : moyenne des 5 jours de bourse precedant le versement)",
    "TD.TO": "P-5..P-1 (circulaire TD : 5 jours de bourse avant la date de placement)",
    "BMO.TO": "P-5..P-1 (prospectus BMO : 5 jours de bourse precedant la periode de placement)",
    "BCE.TO": "P-5..P-1 (circulaire BCE 2024 : 5 jours de bourse precedant le versement)",
    "PPL.TO": "regle Pembina : du max(21e jour ouvrable avant P, 2e jour ouvrable apres la date de cloture) a P-2",
}
DEFAULT_WINDOW = "P-5..P-1 (defaut du preenregistrement ; definition exacte de la circulaire non consultee)"

PAY_FILTERS = {  # keep only the common-share payment dates of each issuer
    "RY.TO": lambda d: d.month in (2, 5, 8, 11),
    "TD.TO": lambda d: d.month in (1, 4, 7, 10),
    "BMO.TO": lambda d: d.month in (2, 5, 8, 11),
    "BNS.TO": lambda d: d.month in (1, 4, 7, 10) and d.day >= 20,
    "CM.TO": lambda d: d.month in (1, 4, 7, 10),
    "MFC.TO": lambda d: d.month in (3, 6, 9, 12) and d.day >= 15,
    "SLF.TO": lambda d: d.month in (3, 6, 9, 12) and d.day >= 27 and d.weekday() < 5,
    "ENB.TO": lambda d: d.month in (3, 6, 9, 12) and d.day == 1,
    "TRP.TO": lambda d: d.month in (1, 4, 7, 10) and d.day >= 27,
    "PPL.TO": lambda d: 13 <= d.day <= 17,
    "BCE.TO": lambda d: d.month in (1, 4, 7, 10) and d.day == 15,
    "T-A.TO": lambda d: d.month in (1, 4, 7, 10) and d.day <= 5,
    "T.TO": lambda d: d.month in (1, 4, 7, 10) and d.day <= 5,
}

SCRATCH_FILES = {  # pay-date extractions produced during step 0 (decl, pay, url[, drip])
    "RY.TO": ["pd_ry.tsv"], "TD.TO": [], "BMO.TO": ["pd_bmo.tsv"], "BNS.TO": ["pd_bns.tsv"], "CM.TO": ["pd_cm.tsv"],
    "MFC.TO": ["pd_mfc.tsv"], "SLF.TO": ["pdx_slf.tsv"], "ENB.TO": ["pdx_enb.tsv"], "TRP.TO": ["pdx_trp.tsv"],
    "PPL.TO": ["pd_ppl.tsv"], "T.TO": ["pd_t.tsv"],
}


# =================================================================================== export (scratch -> repo)
def _d(s):
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def export(scratch: Path):
    sys.path.insert(0, str(scratch / "tools"))
    import web  # noqa: E402  (scratch helper: cached official documents)
    SRC.mkdir(parents=True, exist_ok=True)
    rows = []
    for t, files in SCRATCH_FILES.items():
        for f in files:
            for line in (scratch / f).read_text(encoding="utf8").splitlines():
                p = line.split("\t")
                if len(p) < 3 or p[1] == "None":
                    continue
                rec = ""
                if t == "PPL.TO":
                    m = re.search(r"of record (?:at the close of business )?on (\w+ \d{1,2}, \d{4})",
                                  re.sub(r"\s+", " ", web.text(p[2])))
                    if m:
                        try:
                            rec = str(datetime.strptime(m.group(1), "%B %d, %Y").date())
                        except ValueError:
                            rec = ""
                rows.append({"ticker": t, "decl_date": p[0], "pay_date": p[1], "record_date": rec, "url": p[2]})
    # TD: official dividend-history PDF
    for line in (scratch / "pay_td.tsv").read_text(encoding="utf8").splitlines():
        d, _amt, url = line.split("\t")
        rows.append({"ticker": "TD.TO", "decl_date": "", "pay_date": d, "record_date": "", "url": url})
    # BCE: official DRP purchase-price history PDF
    txt = web.text(U["BCE_HIST"])
    for m in re.finditer(r"(Jan|April|July|Oct) 15, ?(\d{4})", txt):
        y = int(m.group(2))
        if 2000 <= y <= 2025:
            mo = {"Jan": 1, "April": 4, "July": 7, "Oct": 10}[m.group(1)]
            rows.append({"ticker": "BCE.TO", "decl_date": "", "pay_date": str(date(y, mo, 15)), "record_date": "",
                         "url": U["BCE_HIST"]})
    rows.append({"ticker": "BCE.TO", "decl_date": "2025-05-07", "pay_date": "2025-07-15", "record_date": "",
                 "url": U["BCE_PAGE"]})
    rows.append({"ticker": "RY.TO", "decl_date": "2009-12-04", "pay_date": "2009-05-22", "record_date": "",
                 "url": U["RY_AR2009"]})
    df = pd.DataFrame(rows)
    df.to_csv(SRC / "pay_dates.csv", index=False)
    # Australia (ASX Appendix 3A.1)
    au = pd.read_csv(scratch / "asx_au.tsv", sep="\t", dtype=str).fillna("")
    au.drop(columns=["method", "further"]).to_csv(SRC / "asx_appendix3a1.csv", index=False)
    print("exported", len(df), "pay rows;", len(au), "ASX rows")


# =================================================================================== build
def _parse_au_date(s: str):
    s = s.strip()
    for f in ("%d/%m/%Y", "%A %B %d, %Y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def build():
    pdates = pd.read_csv(SRC / "pay_dates.csv", dtype=str).fillna("")
    out = []
    for t in sorted(set(pdates["ticker"])):
        sub = pdates[pdates["ticker"] == t].copy()
        sub["pd"] = sub["pay_date"].map(_d)
        sub = sub[sub["pd"].notna()]
        sub = sub[sub["pd"].map(PAY_FILTERS[t])]
        sub = sub[(sub["pd"] >= date(2000, 1, 1)) & (sub["pd"] <= date(2026, 10, 9))]
        # prefer the dividend-declaration release as row source
        sub["pref"] = ~sub["url"].str.contains("dividend|declares|notice-of-cash", case=False)
        sub["ym"] = sub["pd"].map(lambda x: (x.year, x.month))
        sub = sub.sort_values(["ym", "pref", "pd"]).drop_duplicates("ym", keep="first")
        # TELUS: before Feb 2013 the DRIP bought/issued non-voting shares (T.A)
        for _, r in sub.iterrows():
            tick = t
            if t == "T.TO" and r["pd"] < date(2013, 2, 4):
                tick = "T-A.TO"
            out.append((tick, r))
    rows = []
    for tick, r in out:
        reg = [g for g in REGIMES if g[0] == tick and _d(g[1]) <= r["pd"] <= _d(g[2])]
        name, group = ISSUERS[tick]
        base = {"country": "CA", "issuer": name, "ticker": tick, "group": group, "decl_date": r["decl_date"],
                "pay_date": str(r["pd"]), "record_date": r["record_date"],
                "window_a_def": WINDOW_DEF.get(tick, DEFAULT_WINDOW), "window_a_start": "", "window_a_end": "",
                "souscripteur": "", "url_source": r["url"]}
        if reg:
            g = reg[0]
            base.update({"source_achat": g[3], "rabais_pct": g[4], "statut_doc": g[5], "url_regime": U[g[6]],
                         "notes": g[7]})
        else:
            base.update({"source_achat": "", "rabais_pct": "", "statut_doc": "non_documente", "url_regime": "",
                         "notes": "date de versement trouvee, traitement DRIP non documente"})
        rows.append(base)
    # Australia
    au = pd.read_csv(SRC / "asx_appendix3a1.csv", dtype=str).fillna("")
    au["pd"] = au["payment"].map(_parse_au_date)
    au = au[au["pd"].notna()]
    au["is_update"] = au["title"].str.startswith("Update")
    au = au.sort_values(["code", "pd", "is_update", "ann_date"]).drop_duplicates(["code", "pd"], keep="last")
    for _, r in au.iterrows():
        per = [x for x in (_parse_au_date(s) for s in r["period"].split(";")) if x]
        if len(per) < 2:
            continue
        tick = f"{r['code']}.AX"
        name, group = ISSUERS[tick]
        disc = float(r["discount"]) if r["discount"] else None
        rows.append({"country": "AU", "issuer": name, "ticker": tick, "group": group, "decl_date": "",
                     "pay_date": str(r["pd"]), "record_date": "",
                     "window_a_def": "periode de calcul du prix DRP (Appendix 3A.1, partie 4A.4)",
                     "window_a_start": str(min(per)), "window_a_end": str(max(per)),
                     "source_achat": "tresor" if r["issue"] == "Yes" else ("marche" if r["issue"] == "No" else "non_precise"),
                     "rabais_pct": disc if disc is not None else "",
                     "statut_doc": "explicite" if disc is not None else "non_documente",
                     "souscripteur": "oui" if r["underwrit"] == "yes" else "non",
                     "url_source": r["pdf"], "url_regime": r["pdf"],
                     "notes": "DRP souscrit par un preneur ferme" if r["underwrit"] == "yes" else ""})
    ev = pd.DataFrame(rows).sort_values(["country", "ticker", "pay_date"]).reset_index(drop=True)
    ev.insert(0, "event_id", [f"E{i:04d}" for i in range(1, len(ev) + 1)])
    cols = ["event_id", "country", "issuer", "ticker", "group", "decl_date", "pay_date", "record_date",
            "window_a_def", "window_a_start", "window_a_end", "source_achat", "rabais_pct", "statut_doc",
            "souscripteur", "url_source", "url_regime", "notes"]
    ev[cols].to_csv(OUT, index=False)
    ca = ev[ev["country"] == "CA"]
    usable = ca[ca["statut_doc"] != "non_documente"]
    nd = (pd.to_numeric(usable["rabais_pct"]) > 0).sum()
    print(f"CA rows {len(ca)}, documented {len(usable)}, with discount {nd}; AU rows {(ev['country'] == 'AU').sum()}")
    print(usable.assign(D=pd.to_numeric(usable["rabais_pct"]) > 0).groupby(["ticker", "D"]).size().to_string())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "build"])
    ap.add_argument("--scratch", default="")
    a = ap.parse_args(argv)
    if a.cmd == "export":
        export(Path(a.scratch))
    else:
        build()


if __name__ == "__main__":
    main()
