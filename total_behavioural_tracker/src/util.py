import os
import time
import json
import csv
import pandas as pd
from matplotlib import pyplot as plt
import seaborn as sns
from pathlib import Path
from kivy.resources import resource_add_path, resource_find


resource_add_path(os.path.join(os.getcwd(), "data"))


def find_file(filename):
    file = Path(resource_find(filename))
    if not file.exists():
        raise FileNotFoundError(f"Configuration file not found: {file}")
    return file


def load_json(filename) -> dict:
    # TODO: GET this file from server
    return json.load(open(filename))


def write_data(data, filename):
    # TODO: POST this file to server
    json.dump(data, open(filename, "w"))


# THIS SHOULD ALL COME FROM THE **SERVER**
DAT_FILE = find_file("program_data.csv")
IMG_FILE = find_file("program_graph.png")
PROGRAM_FILE = find_file("program_cfg.json")
CFG_FILE = find_file("app_cfg.json")
ProgramCFG = load_json(PROGRAM_FILE)
# This might just need to be a python dictionary...
GlobalCFG = load_json(CFG_FILE)

PlotCFG, ClassesCFG, MeasureCFG, ConfigCFG, AboutCFG, MCFG = (
    GlobalCFG["util"]["plot"],
    GlobalCFG["classes"],
    GlobalCFG["measure"],
    GlobalCFG["cfg"],
    GlobalCFG["about"],
    GlobalCFG["main"],
)


def load_variable_data(varname) -> dict:
    return ProgramCFG[varname]


def update_var_key_data(var_name: str, key: str, new_data: list) -> None:
    temp = {}
    for var in ProgramCFG.keys():
        temp[var] = ProgramCFG[var]
        if var == var_name:
            temp[var][key]["user"] = new_data
    write_data(temp, PROGRAM_FILE)


def unconfigured_vars():
    vars, unconfigured = (
        list(ProgramCFG.keys()),
        [],
    )
    for v in vars:
        for v in load_variable_data(v).values():
            if not v["user"]:
                unconfigured.append(v)
    return unconfigured


def store_measurement(data: list) -> None:
    with open(DAT_FILE, "a+", newline="") as f:
        if f.read(1) != "\n":
            f.write("\n")
        writer = csv.writer(f)
        writer.writerow([get_date()] + data)


def get_date() -> str:
    return "-".join([str(i) for i in time.localtime()[:3]])


def new_entry_valid() -> bool:
    df = get_formatted_df()
    if df.empty:
        return True
    l_row = df.index[-1]
    last_entry_today = (
        str(l_row).split()[0] == str(pd.to_datetime(get_date())).split()[0]
    )
    return False if last_entry_today else True


def overwrite_last_entry() -> None:
    df = get_formatted_df()
    df = df.drop(df.index[-1])
    df.to_csv(DAT_FILE)


def create_field_questions(prefix: str, entries: list, suffix: str) -> list:
    if not suffix:
        suffix = "?"
    return list(map(lambda x: " ".join([prefix, x, suffix]), entries))


def mk_questions(cfg_file: str, prompts_cfg: list) -> list:
    file, q = load_variable_data(cfg_file), []
    for pre, field, suf in prompts_cfg:
        q += create_field_questions(pre, file[field]["user"], suf)
    return q


def will_power() -> float:
    return mk_questions("willpower", [("Do you want to", "Desires", None)])


def neg_reinforcement() -> float:
    dq_args, dr_args = list(
        tuple(
            zip(
                ["Are you"] * 3,
                ["Restrictions", "Boundaries", "Accountability"],
                3 * [None],
            )
        )
    ), [("Have you", "Relapse", None)]
    return mk_questions("negative reinforcement", dq_args + dr_args)


def obsession() -> float:
    args = [
        ("Did you forget to take your medication to manage", "Mental", None),
        ("Are you addicted to", "Addiction", None),
    ]
    return mk_questions("obsession", args)


def pos_reinforcement() -> float:
    args = [
        ("Have you lived in accordance with", "Values", None),
        ("Have you done your daily", "Daily", None),
        ("Have you been a part of a", "Fellowship", "fellowship today?"),
    ]
    return mk_questions("positive reinforcement", args)


def normalize_as_pct(
    val: float or int, min_val: float or int, val_range: float or int
) -> int:
    return round(100 * ((val - min_val) / val_range))


def get_formatted_df() -> pd.DataFrame:
    df = pd.read_csv(DAT_FILE)
    ys = [i for i in df.columns if i != "date"]
    df.set_index("date", inplace=True)
    if not df.empty:
        df.index = pd.to_datetime(df.index, yearfirst=True)
        df = df[ys]
    else:
        df = pd.DataFrame(columns=ys)
        df.index = pd.to_datetime([])
    return df


def get_warn_index(df):
    df_index = df.index
    min_date, max_date = min(df_index), max(df_index)
    return min_date + (PlotCFG["offset_dist"] * (max_date - min_date))


def set_plot_options(df: pd.DataFrame) -> None:
    WARN = PlotCFG["warning"]
    LEG = PlotCFG["legend"]
    AXES = PlotCFG["axes"]
    sns.set_theme(context="notebook", style="darkgrid", palette="muted")
    if not df.empty:
        df.plot(style=["ms-", "go-", "y^-", "bs-", "rs-"])
        plt.text(
            x=get_warn_index(df),
            y=15,
            s="Relapse Danger Zone",
            fontsize=WARN["font_size"],
            va="center",
            ha="center",
        )
        plt.axhspan(ymin=0, ymax=25, color=WARN["color"], alpha=WARN["opacity"])
        plt.legend(loc=LEG["loc"], fontsize=LEG["font_size"])
    plt.xlabel("Time", fontsize=AXES["font_size"])
    plt.ylabel("Total % Value", fontsize=AXES["font_size"])

    ax = plt.gca()
    ax.tick_params(axis="x", labelsize=AXES["tick_font_size"])
    ax.tick_params(axis="y", labelsize=AXES["tick_font_size"])


def store_daily_visualization() -> None:
    df = get_formatted_df()
    set_plot_options(df)
    plt.savefig(IMG_FILE)
