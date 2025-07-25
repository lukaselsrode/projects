import yaml
import re
import os
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from typing import Dict, Optional


root_dir = "/".join(os.path.abspath(__file__).split("/")[:-2])
investments_file = "/".join([root_dir, "investments.yaml"])


def load_cfg(filename):
    with open(filename, "r") as file:
        return yaml.safe_load(file)


# Load the full configuration file
config = load_cfg(investments_file)

# Extract the main configuration and sector configurations
app_config = config.get('config', {})
inv_cfg = {k: v for k, v in config.items() if k != 'config'}

# Make config values easily accessible
IGNORE_NEGATIVE_PE = app_config.get('ignore_negative_pe', False)
IGNORE_NEGATIVE_PB = app_config.get('ignore_negative_pb', False)
DIVIDEND_THRESHOLD = app_config.get('dividend_threshold', 2.5)
METRIC_THRESHOLD = app_config.get('metric_threshold', 4)
SELLOFF_THRESHOLD = app_config.get('selloff_threshold', 30)
WEEKLY_INVESTMENT = str(app_config.get('weekly_investment', 400))
INDEX_PCT = app_config.get('index_pct', 0.85)
ETFS = app_config.get('etfs', ['SPY', 'VOO', 'VTI', 'QQQ', 'SCHD'])


def split_string_to_set(input_string):
    separators = r"[\/ :&]+"
    substrings = set(re.split(separators, input_string))
    return substrings


def get_investment_ratios(sector, industry=None):
    # Default ratios if no sector/industry matches are found 
    DEFAULT_RATIOS = [15.0, 2.5]  # [P/E, P/B] - conservative defaults
    
    if not sector or sector not in inv_cfg:
        return DEFAULT_RATIOS
        
    default = inv_cfg[sector].get('default', DEFAULT_RATIOS)
    
    if not industry:
        return default

    def makeshift_ratios(ratios):
        return [
            ratios[0] if ratios and len(ratios) > 0 and ratios[0] is not None else default[0],
            ratios[1] if ratios and len(ratios) > 1 and ratios[1] is not None else default[1],
        ]

    # direct match
    if industry in inv_cfg[sector] and inv_cfg[sector].get(industry):
        return makeshift_ratios(inv_cfg[sector][industry])

    # Fuzzy match
    try:
        stdin_set = split_string_to_set(industry)
        min_diff = float('inf')
        match = None
        
        for ind in inv_cfg[sector]:
            if ind == 'default':
                continue
                
            ind_set = split_string_to_set(ind)
            diff = len(stdin_set.difference(ind_set))

            if not diff and len(ind_set) == len(stdin_set):
                return makeshift_ratios(inv_cfg[sector][ind])

            if diff < min_diff:
                min_diff = diff
                match = ind
                
        if match and min_diff < 3:  # Only use fuzzy match if it's a close match
            return makeshift_ratios(inv_cfg[sector][match])
            
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Error in fuzzy matching industry '{industry}': {str(e)}")
    
    return default  # Return sector default if no good match found


def fetch_finviz_data(url: str) -> Dict[str, Dict[str, Optional[float]]]:
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find('div',class_="content").find('table',class_="styled-table-new is-medium is-rounded is-tabular-nums w-full groups_table")
    if not table:
        raise ValueError("Could not find data table in Finviz response")
    
    table_data = table.find_all("tr")[1:] 

    result = {}
    for data in table_data:
        if data.find('a'):
            pe = data.find_all("td")[3].get_text()
            pb = data.find_all("td")[7].get_text()
            result[data.find('a').get_text()] = {'PE': float(pe) if pe != '-' else None, 'PB' :float(pb) if pb != '-' else None}
        
    return result


def update_industry_valuations(verbose: bool = True) -> None:
    # URLs for Finviz group data
    SECTOR_URL = "https://finviz.com/groups.ashx?g=sector&v=120&o=pe"
    INDUSTRY_URL = "https://finviz.com/groups.ashx?g=industry&v=120&o=pe"
    
    # Mapping for sector names (YAML -> Finviz)
    SECTOR_MAP = {
        'Materials': 'Basic Materials',
        'Consumer Discretionary': 'Consumer Cyclical',
        'Consumer Staples': 'Consumer Defensive',
        'Financials': 'Financial',
        'Health Care': 'Healthcare',
        'Information Technology': 'Technology',
        'Real Estate': 'Real Estate',
        'Utilities': 'Utilities',
        'Energy': 'Energy',
        'Industrials': 'Industrials',
        'Communication Services': 'Communication Services'
    }
    
    INDUSTRY_MAP = {
        "Insurance - Life": "Life Insurance",
        "Insurance - Property & Casualty": "Property & Casualty Insurance",
        "Insurance - Specialty": "Specialty Insurance",
        "Insurance - Diversified": "Diversified Insurance",
        "REIT - Mortgage": "Mortgage REITs",
        "REIT - Diversified": "Diversified REITs",
        "REIT - Retail": "Retail REITs",
        "REIT - Residential": "Residential REITs",
        "REIT - Industrial": "Industrial REITs",
        "REIT - Office": "Office REITs",
        "REIT - Hotel & Motel": "Hotel & Motel REITs",
        "REIT - Healthcare Facilities": "Health Care REITs",
        "REIT - Specialty": "Specialty REITs",
        "Oil & Gas E&P": "Oil & Gas Exploration & Production",
        "Beverages - Brewers": "Brewers",
        "Beverages - Wineries & Distilleries": "Distillers & Vintners",
        "Beverages - Non-Alcoholic": "Non-Alcoholic Beverages",
        "Telecom Services": "Telecommunication Services",
        "Internet Content & Information": "Interactive Media & Services",
        "Software - Application": "Application Software",
        "Software - Infrastructure": "Systems Software"
    }
    
    try:
        # Fetch sector and industry data
        sector_data = fetch_finviz_data(SECTOR_URL)
        industry_data = fetch_finviz_data(INDUSTRY_URL)
        
        # Load existing config
        config = load_cfg(investments_file)
        
        # Track changes for logging
        changes = []
        
        # Debug: Print available sectors from both sources
        if verbose:
            print("\n=== Available Sectors ===")
            print("From Finviz:", ", ".join(sorted(sector_data.keys())))
            print("From YAML:", ", ".join(k for k in config.keys() if k != 'config'))
            print("\n=== Sector Mappings ===")
            for yaml_name, finviz_name in SECTOR_MAP.items():
                print(f"YAML: {yaml_name:25} -> Finviz: {finviz_name}")
        
        # Track which sectors we've found matches for
        matched_sectors = set()
        
        # Update sector-level data
        for sector_yaml, industries in config.items():
            if sector_yaml == 'config':
                continue
                
            # Map YAML sector name to Finviz sector name
            finviz_sector = SECTOR_MAP.get(sector_yaml)
            
            if verbose:
                print(f"\nProcessing YAML sector: {sector_yaml} (maps to Finviz: {finviz_sector})")
            
            if finviz_sector and finviz_sector in sector_data:
                matched_sectors.add(finviz_sector)
                new_pe = sector_data[finviz_sector]["PE"]
                new_pb = sector_data[finviz_sector]["PB"]
                
                if verbose:
                    print(f"  Found matching Finviz sector: {finviz_sector}")
                    print(f"  PE: {new_pe}, PB: {new_pb}")
                new_pe = sector_data[src_sector]["PE"]
                new_pb = sector_data[src_sector]["PB"]
                
                # Update default ratio if it exists
                if 'default' in industries and isinstance(industries['default'], list):
                    old_pe, old_pb = industries['default']
                    
                    # Only update if values have changed
                    pe_changed = new_pe is not None and new_pe != old_pe
                    pb_changed = new_pb is not None and new_pb != old_pb
                    
                    if pe_changed or pb_changed:
                        old_values = f"PE: {old_pe:.2f}, PB: {old_pb:.2f}"
                        new_pe_val = new_pe if pe_changed else old_pe
                        new_pb_val = new_pb if pb_changed else old_pb
                        industries['default'] = [new_pe_val, new_pb_val]
                        
                        change_info = {
                            'type': 'sector',
                            'name': sector_yaml,
                            'finviz_name': finviz_sector,
                            'old_values': old_values,
                            'new_values': f"PE: {new_pe_val:.2f}, PB: {new_pb_val:.2f}",
                            'source': 'Finviz',
                            'timestamp': str(datetime.now())
                        }
                        changes.append(change_info)
                        
                        if verbose:
                            print(f"  Updated {sector_yaml} default ratios")
                            print(f"    Old: {old_values}")
                            print(f"    New: PE: {new_pe_val:.2f}, PB: {new_pb_val:.2f}")
                    else:
                        if verbose:
                            print(f"  No changes for {sector_yaml} default ratios")
                elif verbose:
                    print(f"  No default ratios found for {sector_yaml}")
            
            # Update industry data
            for industry_yaml, metrics in industries.items():
                if industry_yaml == 'default' or not isinstance(metrics, list) or len(metrics) < 2:
                    continue
                    
                # Map industry name if needed
                src_industry = INDUSTRY_MAP.get(industry_yaml, industry_yaml)
                
                if src_industry in industry_data:
                    new_pe = industry_data[src_industry]["PE"]
                    new_pb = industry_data[src_industry]["PB"]
                    
                    # Only update if values have changed
                    pe_changed = new_pe is not None and new_pe != metrics[0]
                    pb_changed = new_pb is not None and new_pb != metrics[1]
                    
                    if pe_changed or pb_changed:
                        old_values = f"PE: {metrics[0]:.2f}, PB: {metrics[1]:.2f}"
                        
                        if pe_changed:
                            metrics[0] = new_pe
                        if pb_changed:
                            metrics[1] = new_pb
                            
                        change_info = {
                            'type': 'industry',
                            'sector': sector_yaml,
                            'name': industry_yaml,
                            'old_values': old_values,
                            'new_values': f"PE: {metrics[0]:.2f}, PB: {metrics[1]:.2f}",
                            'source': 'Finviz',
                            'timestamp': str(datetime.now())
                        }
                        changes.append(change_info)
        
        # Print summary of matched sectors
        if verbose:
            print("\n=== Sector Matching Summary ===")
            print(f"Matched {len(matched_sectors)}/{len(sector_data)} Finviz sectors")
            unmatched = set(sector_data.keys()) - matched_sectors
            if unmatched:
                print("Unmatched Finviz sectors:", ", ".join(sorted(unmatched)))
        
        # Save the updated config
        if changes:
            with open(investments_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
            if verbose:
                print("\n=== Industry Valuation Updates ===")
                print(f"Updated {len(changes)} valuations")
                for change in changes:
                    if change['type'] == 'sector':
                        print(f"\nSector: {change['name']}")
                        if 'finviz_name' in change:
                            print(f"  Finviz: {change['finviz_name']}")
                    else:
                        print(f"\nSector: {change['sector']} | Industry: {change['name']}")
                    print(f"  Old: {change['old_values']}")
                    print(f"  New: {change['new_values']}")
                    print(f"  Source: {change['source']} at {change['timestamp']}")
                print("\n=== Update Complete ===")
            
            logging.info(f"Updated {len(changes)} industry valuations in investments.yaml")
        else:
            if verbose:
                print("\nNo changes detected in industry valuations.")
                print("This could be because:")
                print("1. The ratios in the YAML file already match Finviz")
                print("2. The sector/industry names don't match between sources")
                print("3. There was an error in the mapping")
            logging.info("No changes detected in industry valuations")
        
    except Exception as e:
        logging.error(f"Failed to update industry valuations: {str(e)}")
        if verbose:
            print(f"Error updating industry valuations: {str(e)}")
        raise
