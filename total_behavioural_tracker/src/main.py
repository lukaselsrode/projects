import time
import os
import yaml
import csv
import pandas as pd
from matplotlib import pyplot as plt
import seaborn as sns
from webbrowser import open_new_tab as urlopen
from kivy.app import App
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.uix.dropdown import DropDown


def load_yaml_file(file_path: str) -> dict:
    with open(file_path, "r") as file:
        return yaml.safe_load(file)


GlobalCFG = load_yaml_file("config/app_cfg.yaml")
PATHS, PlotCFG, ClassesCFG, MeasureCFG, ConfigCFG, AboutCFG, MCFG = (
    GlobalCFG["paths"],
    GlobalCFG["util"]["plot"],
    GlobalCFG["classes"],
    GlobalCFG["measure"],
    GlobalCFG["cfg"],
    GlobalCFG["about"],
    GlobalCFG["main"],
)

DAT_FILE = PATHS["data"]
IMG_FILE = PATHS["img"]
VARS_DIR = PATHS["vars_dir"]


def load_variable_data(varname) -> dict:
    # load the data from the file
    with open("".join([VARS_DIR, varname, ".yaml"]), "r") as cfgfile:
        cfg = yaml.safe_load(cfgfile)
    return cfg


def update_var_key_data(var_name: str, key: str, new_data: list) -> None:
    cfg_file = "".join([VARS_DIR, var_name, ".yaml"])
    with open(cfg_file, "r") as f:
        data = yaml.safe_load(f)
    data[key]["user"] = new_data
    with open(cfg_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def unconfigured_vars():
    vars, unconfigured = (
        list(map(lambda i: i.split(".")[0], os.listdir(PATHS["vars_dir"]))),
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
    return min_date + 2 * (max_date - min_date) / 3


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


TITLE = ClassesCFG["title"]
EXIT = ClassesCFG["exit"]
POPUP = ClassesCFG["popup"]
BUTTONS = ClassesCFG["2butn"]


class PageTitle(Label):
    def __init__(self, **kwargs):
        super(PageTitle, self).__init__(**kwargs)
        self.italic = True
        self.pos_hint = {"x": 0.4, "y": 0}
        self.size_hint = TITLE["size"]
        self.color = TITLE["color"]
        self.font_size = TITLE["font_size"]


class ExitButton(Button):
    def __init__(self, application, **kwargs):
        super(ExitButton, self).__init__(**kwargs)
        self.app = application
        self.layout = AnchorLayout(
            anchor_x="right", anchor_y="top", size_hint=EXIT["lsize"]
        )
        self.button = Button(
            text="Back", size_hint=EXIT["bsize"], background_color=EXIT["bcolor"]
        )
        self.button.bind(on_release=self.exit_app)
        self.layout.add_widget(self.button)

    def exit_app(self, instance):
        self.app.stop()


class PopPrompt(Button):
    def __init__(self, title, prompt, yfunc, nfunc, **kwargs):
        super(PopPrompt, self).__init__(**kwargs)
        self.layout = BoxLayout(orientation="vertical", padding=POPUP["padding"])
        self.msg = Label(text=prompt)
        self.btn_layout = BoxLayout(
            size_hint_y=None, height=POPUP["height"], spacing=POPUP["space"]
        )
        yes_btn = Button(text="Yes", on_release=yfunc, italic=True)
        no_btn = Button(text="No", on_release=nfunc, italic=True)
        self.btn_layout.add_widget(yes_btn)
        self.btn_layout.add_widget(no_btn)
        self.layout.add_widget(self.msg)
        self.layout.add_widget(self.btn_layout)
        self.popup = Popup(
            title=title,
            content=self.layout,
            size_hint=(None, None),
            size=POPUP["size"],
            auto_dismiss=False,
        )
        self.popup.open()

    def dismiss(self):
        self.popup.dismiss()


class OneButtonPopup(Popup):
    def __init__(self, title, message, **kwargs):
        super().__init__(title=title, size_hint=(None, None), size=(400, 300), **kwargs)
        self.content = BoxLayout(orientation="vertical")
        self.message_label = Label(text=message)
        self.close_button = Button(text="Close", size_hint=(1, 0.2))
        self.close_button.bind(on_press=self.dismiss)
        self.content.add_widget(self.message_label)
        self.content.add_widget(self.close_button)


class BigButton(Button):
    def __init__(self, txt, func, **kwargs):
        super(BigButton, self).__init__(**kwargs)
        self.text = txt
        self.italic = True
        self.size_hint = BUTTONS["button"]["size"]
        self.font_size = BUTTONS["button"]["font_size"]
        self.bind(on_release=func)


class TwoButtonLayout(BoxLayout):
    def __init__(self, rtxt, rfunc, ltxt, lfunc, **kwargs):
        super(TwoButtonLayout, self).__init__(**kwargs)
        self.orientation = BUTTONS["layout"]["orientation"]
        self.size_hint = BUTTONS["layout"]["size"]
        self.spacing = BUTTONS["layout"]["spacing"]
        self.right_button = BigButton(
            txt=rtxt, func=rfunc, background_color=BUTTONS["button"]["rcolor"]
        )
        self.left_button = BigButton(
            txt=ltxt, func=lfunc, background_color=BUTTONS["button"]["lcolor"]
        )
        self.add_widget(self.left_button)
        self.add_widget(self.right_button)


class BaseApp(App):
    def close(self):
        self.root.clear_widgets()
        self.stop()

    def build(self):
        raise NotImplementedError("Must be implemented by subclasses")


PAGE_LAYOUT = MeasureCFG["layout"]
QUESTION = MeasureCFG["question"]


class QuestionView(GridLayout):
    def __init__(self, app, **kwargs):
        super(QuestionView, self).__init__(**kwargs)
        self.app = app
        self.var = self.app.vars[self.app.var_index]
        self.question = self.var.questions[self.app.q_index]
        self.cols, self.rows = PAGE_LAYOUT

        self.exit = ExitButton(self.app)
        self.add_widget(self.exit.layout, index=0)

        self.question_label = Label(
            text=self.question,
            font_size=QUESTION["font_size"],
            halign="center",
            valign="middle",
            size_hint_y=QUESTION["size_y"],
            color="yellow",
            italic=True,
        )
        self.question_label.bind(size=self.question_label.setter("text_size"))
        self.add_widget(self.question_label)

        self.buttons_layout = TwoButtonLayout(
            rtxt="YES", rfunc=self.on_yes, ltxt="NO", lfunc=self.on_no
        )
        self.add_widget(self.buttons_layout)

    def on_yes(self, instance):
        self.var.add_score(1)
        self.app.next_screen()

    def on_no(self, instance):
        self.app.next_screen()


class VarMeasurer:
    def __init__(self, questions):
        self.questions, self.score = questions, 0
        self.n = len(questions)

    def add_score(self, score):
        self.score += score

    def norm_score(self):
        return normalize_as_pct(self.score / self.n, 0, 1)


class ProgramMeasurementApp(BaseApp):
    def __init__(self, **kwargs):
        super(ProgramMeasurementApp, self).__init__(**kwargs)

        self.wp = VarMeasurer(will_power())
        self.o = VarMeasurer(obsession())
        self.nr = VarMeasurer(neg_reinforcement())
        self.pr = VarMeasurer(pos_reinforcement())

        self.vars = [self.wp, self.nr, self.o, self.pr]
        self.q_index = self.var_index = 0

    def clear_to_next_question(self):
        self.root.clear_widgets()
        self.root.add_widget(self.current_question_view())

    def current_question_view(self):
        return QuestionView(self)

    def next_var(self):
        self.var_index += 1
        self.q_index = 0

    def process_questions(self):
        wp, nr, o, pr = list(map(lambda x: x.norm_score(), self.vars))
        program = normalize_as_pct(wp + nr - (o - pr), -100, 400)
        store_measurement([wp, nr, o, pr, program])

    def next_screen(self):
        self.q_index += 1
        if self.q_index < self.vars[self.var_index].n:
            self.clear_to_next_question()
            return
        self.next_var()
        if self.var_index < len(self.vars):
            self.clear_to_next_question()
            return
        self.process_questions()
        self.close()

    def build(self):
        return self.current_question_view()


GRID_LAYOUT = ConfigCFG["layout"]
TEXT = ConfigCFG["text"]


class ConfigureVarKeyView(GridLayout):
    def __init__(self, file, var, data, app, **kwargs):
        super(ConfigureVarKeyView, self).__init__(**kwargs)

        self.app, self.var, self.data, self.file = app, var, data, file
        self.cols, self.padding, self.spacing = GRID_LAYOUT

        self.exit = ExitButton(self.app)
        self.add_widget(self.exit.layout, index=0)

        self.config_label = PageTitle(text=var)
        self.add_widget(self.config_label)

        self.config_explanation = Label(
            text=data["ex"],
            font_size=TEXT["explanation"]["font_size"],
            italic=True,
            valign="middle",
            halign="center",
        )
        self.add_widget(self.config_explanation)

        self.config_input = TextInput(
            hint_text="Click 'Load' for current config or examples",
            multiline=True,
            font_size=ConfigCFG["input"]["font_size"],
        )
        self.add_widget(self.config_input)

        self.button_layout = TwoButtonLayout(
            ltxt="Load",
            lfunc=self.reset_default,
            rtxt="Accept",
            rfunc=self.accept_input,
        )
        self.add_widget(self.button_layout)

    def reset_default(self, instance):
        display_txt = (
            self.data["default"] if not self.data["user"] else self.data["user"]
        )
        self.config_input.text = "\n".join(display_txt).lower()

    def confirm_new_config(self):
        self.popup = PopPrompt(
            title=f"Confirm {self.var} configuration",
            prompt=f"Confirm {self.var} configuration  \n for your {self.file.rstrip('.yaml')}?",
            yfunc=self.write_new_config,
            nfunc=self.cancel_popup,
        )

    def cancel_popup(self, instance):
        if self.popup:
            self.popup.dismiss()

    def write_new_config(self, instance):
        update_var_key_data(self.file, self.var, self.user_input_keys)
        self.popup.dismiss()
        self.app.next_screen()

    def accept_input(self, instance):
        self.user_input_keys = [
            x.lower() for x in self.config_input.text.split("\n") if x
        ]
        if not self.user_input_keys and not self.data["user"]:
            self.user_input_keys = self.data["default"]
        self.confirm_new_config()


class ConfigureApplication(BaseApp):
    def __init__(self, var_file, **kwargs):
        super(ConfigureApplication, self).__init__(**kwargs)
        self.file = var_file
        self.data = load_variable_data(self.file)
        self.vars_list = list(self.data.keys())
        self.current_var_index = 0

    def build(self):
        return self.current_cfg_view()

    def current_cfg_view(self):
        var = self.vars_list[self.current_var_index]
        return ConfigureVarKeyView(self.file, var, self.data[var], self)

    def next_screen(self):
        self.current_var_index += 1
        if not self.current_var_index < len(self.vars_list):
            self.close()
        self.root.clear_widgets()
        self.root.add_widget(self.current_cfg_view())


URLS = AboutCFG["urls"]
creditor_url = URLS["creditor"]
theory_url = URLS["theory"]
book_url = URLS["book"]
repo_url = URLS["repo"]
tip_url = URLS["tip"]


class HyperlinkLabel(Label):
    def __init__(self, **kwargs):
        super(HyperlinkLabel, self).__init__(**kwargs)
        self.markup = True
        self.font_size = AboutCFG["description"]["font_size"]
        self.halign, self.valign = "center", "middle"
        self.text_size = self.width, None

    def on_size(self, *args):
        self.text_size = self.width, None

    def on_ref_press(self, ref):
        urlopen(ref)


class About(BaseApp):
    def build(self):
        layout = BoxLayout(orientation="vertical")
        exit = ExitButton(self)
        title_label = PageTitle(text="About The Total Behavioral Tracker App")
        credit_txt = HyperlinkLabel(
            text=f"""Credit goes to {hyperlink_fmt('Micheal Lenok', creditor_url)} an Addiction and Mental Health Counselor at the Sylvia Brafman Mental Health Center, for his work creating the 'program equation' based on {hyperlink_fmt("Glasser's work on 'choice theory'", theory_url)} combined with his own personal and professional experience detailed fully in his recent book {hyperlink_fmt("<BOOK HERE>", book_url)}"""
        )
        button_layout = TwoButtonLayout(
            rtxt="Support",
            rfunc=self.open_tip_jar,
            ltxt="Contribute",
            lfunc=self.open_code_repository,
        )
        layout.add_widget(exit.layout, index=0)
        layout.add_widget(title_label)
        layout.add_widget(credit_txt)
        layout.add_widget(button_layout)
        return layout

    def open_code_repository(self, instance):
        urlopen(repo_url)

    def open_tip_jar(self, instance):
        urlopen(tip_url)


def hyperlink_fmt(text, link):
    return f"[color=0000ff][ref={link}][i]{text}[/i][/ref][/color]"


MBUTTONS = MCFG["buttons"]
DROPDOWN = MCFG["dropdown"]
ABOUT = MCFG["about"]


class VariableButton(Button):
    def __init__(self, app, **kwargs):
        super(VariableButton, self).__init__(**kwargs)
        self.size_hint_y, self.height = None, DROPDOWN["height"]
        self.font_size = DROPDOWN["font_size"]
        self.background_color = DROPDOWN["color"]
        self.italic = True
        self.app = app
        self.bind(on_release=self.configure_variable)

    def configure_variable(self, instance):
        self.app.close()
        VarConfig = ConfigureApplication(self.text)
        VarConfig.run(), self.app.run()


class VarsDropDown(DropDown):
    def __init__(self, app, vars, **kwargs):
        super(VarsDropDown, self).__init__(**kwargs)
        for v in vars:
            Vbtn = VariableButton(app, text=v)
            self.add_widget(Vbtn)


class MainButton(Button):
    def __init__(self, **kwargs):
        super(MainButton, self).__init__(**kwargs)
        self.italic = True
        self.size_hint = MBUTTONS["size"]
        self.font_size = MBUTTONS["font_size"]


class MainLineGraph(Image):
    def __init__(self, **kwargs):
        super(MainLineGraph, self).__init__(**kwargs)
        self.source = PATHS["img"]
        self.fit_mode = "fill"


class MainButtonLayout(BoxLayout):
    def __init__(self, app, **kwargs):
        super(MainButtonLayout, self).__init__(**kwargs)
        self.app = app
        self.orientation = "horizontal"
        self.size_hint = MBUTTONS["layout_size"]

        self.about_button = Button(
            text="About",
            size_hint=ABOUT["size"],
            background_color=ABOUT["color"],
            italic=True,
        )
        self.about_button.bind(on_release=self.get_about_page)

        self.configure_button = MainButton(
            text="Configure", background_color=MBUTTONS["cfg_color"]
        )
        self.configure_button.bind(on_press=self.show_cfg_wheel)

        self.measure_button = MainButton(
            text="Measure", background_color=MBUTTONS["measure_color"]
        )
        self.measure_button.bind(on_release=self.measure_prgrm)

        self.add_widget(self.about_button)
        self.add_widget(self.configure_button)
        self.add_widget(self.measure_button)

    def get_about_page(self, instance):
        self.app.close()
        TipJar = About()
        TipJar.run()
        self.app.run()

    def show_cfg_wheel(self, instance):
        vars = list(map(lambda i: i.split(".")[0], os.listdir(PATHS["vars_dir"])))
        dropdown = VarsDropDown(self.app, vars)
        dropdown.bind(
            on_select=lambda instance, x: setattr(self.configure_button, "text", x)
        )
        dropdown.open(self.configure_button)

    def measure_prgrm(self, instance):
        fully_configured = not unconfigured_vars()
        if new_entry_valid() and fully_configured:
            self.start_measurement()
        elif not new_entry_valid() and fully_configured:
            self.confirm_overwrite()
        else:
            popup = OneButtonPopup(
                title="Incomplete Setup", message="Complete Configuration"
            )
            popup.open()

    def start_measurement(self):
        self.app.close()
        Measure = ProgramMeasurementApp()
        Measure.run()
        store_daily_visualization()
        self.linegraph = MainLineGraph()
        self.app.run()

    def confirm_overwrite(self):
        self.popup = PopPrompt(
            title="Confirm Measurement Overwrite",
            prompt="You have already measured your program today.\n Do you want to re-measure it?",
            yfunc=self.on_confirm,
            nfunc=self.on_cancel,
        )

    def on_confirm(self, instance):
        self.popup.dismiss()
        overwrite_last_entry()
        self.start_measurement()

    def on_cancel(self, instance):
        self.popup.dismiss()


class MainPageLayout(BoxLayout):
    def __init__(self, app, **kwargs):
        super(MainPageLayout, self).__init__(**kwargs)
        self.app = app
        self.orientation = "vertical"
        self.app_title = PageTitle(text="Total Behavioural Tracker")
        self.linegraph, self.main_buttons = MainLineGraph(), MainButtonLayout(self.app)
        self.add_widget(self.app_title)
        self.add_widget(self.linegraph)
        self.add_widget(self.main_buttons)


class MainApp(BaseApp):
    store_daily_visualization()

    def build(self):
        return MainPageLayout(self)


if __name__ == "__main__":
    MainApp().run()
