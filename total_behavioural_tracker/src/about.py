from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from classes import BaseScreen, TwoButtonLayout, PageTitle, ExitButton
from webbrowser import open_new_tab as urlopen
from util import get_app_cfg

AboutCFG = get_app_cfg("about")
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


class AboutScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super(AboutScreen, self).__init__(**kwargs)
        self.app = app
        self.layout = BoxLayout(orientation="vertical")
        self.exit = ExitButton(application=self.app)
        self.title_label = PageTitle(text="About The Total Behavioral Tracker App")
        self.credit_txt = HyperlinkLabel(
            text=f"""Credit goes to {hyperlink_fmt('Micheal Lenok', creditor_url)} an Addiction and Mental Health Counselor at the Sylvia Brafman Mental Health Center, for his work creating the 'program equation' based on {hyperlink_fmt("Glasser's work on 'choice theory'", theory_url)} combined with his own personal and professional experience detailed fully in his recent book {hyperlink_fmt("<BOOK HERE>", book_url)}"""
        )
        self.button_layout = TwoButtonLayout(
            rtxt="Support",
            rfunc=self.open_tip_jar,
            ltxt="Contribute",
            lfunc=self.open_code_repository,
        )
        self.layout.add_widget(self.exit.layout, index=0)
        self.layout.add_widget(self.title_label)
        self.layout.add_widget(self.credit_txt)
        self.layout.add_widget(self.button_layout)
        self.add_widget(self.layout)

    def open_code_repository(self, instance):
        urlopen(repo_url)

    def open_tip_jar(self, instance):
        urlopen(tip_url)


def hyperlink_fmt(text, link):
    return f"[color=0000ff][ref={link}][i]{text}[/i][/ref][/color]"
