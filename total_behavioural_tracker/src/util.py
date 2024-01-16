import os
import time
import json
import csv
import pandas as pd
from matplotlib import pyplot as plt
from kivy.app import App
from pathlib import Path
import seaborn as sns
from kivy.resources import resource_find


def find_file(filename):
    try:
        file_path = resource_find(filename)
    except:
        file_path = os.path.join(App.get_running_app().user_data_dir, "data", filename)
    finally:
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", filename)
    file = Path(file_path)
    if file.exists():
        return file
    raise FileNotFoundError(f"file not found: {filename}")



def load_json(filename) -> dict:
    with open(filename, "r") as file:
        return json.load(file)


def get_json_file(filename, key=None):
    load = load_json(find_file(filename))
    return load[key] if key else load


def get_dat_file():
    return find_file("program_data.csv")


def get_img_file():
    return find_file("program_graph.png")


def get_app_cfg(key=None):
    return get_json_file("app_cfg.json", key)


def get_program_cfg(key=None):
    return get_json_file("program_cfg.json", key)


def write_data(data, filename):
    with open(filename, "w") as file:
        return json.dump(data, file)


def store_measurement(data: list) -> None:
    file = get_dat_file()
    with open(file, "a+", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([''])
        writer.writerow([get_date()] + data)


def get_date() -> str:
    return "-".join([str(i) for i in time.localtime()[:3]])


def normalize_as_pct(
    val: float or int, min_val: float or int, val_range: float or int
) -> int:
    return round(100 * ((val - min_val) / val_range))


def get_formatted_df() -> pd.DataFrame:
    file = get_dat_file()
    df = pd.read_csv(file)
    ys = [i for i in df.columns if i != "date"]
    df.set_index("date", inplace=True)
    if not df.empty:
        df.index = pd.to_datetime(df.index, yearfirst=True)
        df = df[ys]
    else:
        df = pd.DataFrame(columns=ys)
        df.index = pd.to_datetime([])
    return df


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
    df.to_csv(get_dat_file())


def create_field_questions(prefix: str, entries: list, suffix: str) -> list:
    if not suffix:
        suffix = "?"
    return list(map(lambda x: " ".join([prefix, x, suffix]), entries))


def update_var_key_data(
    var_name: str,
    key: str,
    new_data: list,
) -> None:
    program_cfg,file = get_program_cfg(),find_file("program_cfg.json")
    temp = {}
    for var in program_cfg.keys():
        temp[var] = program_cfg[var]
        if var == var_name:
            temp[var][key]["user"] = new_data
    write_data(temp, file)


def unconfigured_vars() -> list:
    program_cfg = get_program_cfg()
    vars, unconfigured = (
        list(program_cfg.keys()),
        [],
    )
    for var in vars:
        for v in program_cfg[var].values():
            if not v["user"]:
                unconfigured.append(v)
    return unconfigured


def mk_questions(var: str, prompts_cfg: list) -> list:
    file, q = get_program_cfg(var), []
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


def get_warn_index(df):
    plot_cfg=get_app_cfg()["util"]["plot"]
    df_index = df.index
    min_date, max_date = min(df_index), max(df_index)
    return min_date + (plot_cfg["warning"]["offset_dist"] * (max_date - min_date))


def set_plot_options(df: pd.DataFrame) -> None:
    plot_cfg=get_app_cfg()["util"]["plot"]
    WARN = plot_cfg["warning"]
    LEG = plot_cfg["legend"]
    AXES = plot_cfg["axes"]
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
    plt.savefig(get_img_file())


def update_reccords(data) -> None:
    store_measurement(data)
    store_daily_visualization()
