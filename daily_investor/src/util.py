import yaml
import re
import os

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
