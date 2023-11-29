from webbrowser import open_new_tab as urlopen
from kivy.uix.anchorlayout import AnchorLayout
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

# url configs
creditor_url = "https://www.linkedin.com/in/michael-lenok-4919b659/"
theory_url = "https://en.wikipedia.org/wiki/Glasser's_choice_theory"
book_url = "https://www.amazon.com/"
repo_url = "https://github.com/lukaselsrode/projects/tree/main/total_behavioural_tracker"
tip_url = "https://buy.stripe.com/aEUcN71qN6Pv9Dq6oo"
# description config
DESCRIPTION_FONT_SIZE = 24
# Title config
TITLE_SIZE_HINT = (0.1,0.1)
TITLE_FONT_SIZE = 40
# Buttons config
BUTTONS_SIZE_HINT = (1,0.25)
BUTTONS_SPACING = 10
BUTTON_FONT_SIZE=30
SUPPORT_COLOR, CONTRIBUTE_COLOR = 'green', 'cyan'

def hyperlink_fmt(text, link):
    return f"[color=0000ff][ref={link}][i]{text}[/i][/ref][/color]"

class HyperlinkLabel(Label):
    def __init__(self, **kwargs):
        super(HyperlinkLabel, self).__init__(**kwargs)
        self.markup = True
        self.font_size = DESCRIPTION_FONT_SIZE
        self.halign,self.valign = 'center','middle'
        self.text_size = self.width, None  

    def on_size(self, *args):
        self.text_size = self.width, None  

    def on_ref_press(self, ref):
        urlopen(ref)

class About(App):
    def build(self):
        layout = BoxLayout(orientation="vertical")
        # Exit button
        exit_button_layout = AnchorLayout(anchor_x="right", anchor_y="top", size_hint=(1, 0.1))
        exit_button = Button(text="Back", size_hint=(0.1, 1), background_color="red")
        exit_button.bind(on_release=self.exit_app)
        exit_button_layout.add_widget(exit_button)
        layout.add_widget(exit_button_layout, index=0)
        # Title
        title_label = Label(text="About The Total Behavioral Tracker App", size_hint=TITLE_SIZE_HINT,pos_hint={'x':0.5,'y':0},font_size=TITLE_FONT_SIZE)
        # Credit Blurb
        credit_txt = HyperlinkLabel(text=f"""Credit goes to {hyperlink_fmt('Micheal Lenok',creditor_url)} an Addiction and Mental Health Counselor at the Sylvia Brafman Mental Health Center, for his work creating the 'program equation' based on {hyperlink_fmt("Glasser's work on 'choice theory'",theory_url)} combined with his own personal and professional experience detailed fully in his recent book {hyperlink_fmt("<BOOK HERE>",book_url)}""")
        # Buttons
        button_layout = BoxLayout(size_hint_y=None, size_hint=BUTTONS_SIZE_HINT, spacing=BUTTONS_SPACING)
        # Tip me
        support_button = Button(text="Support this creator",font_size=BUTTON_FONT_SIZE,background_color=SUPPORT_COLOR)
        support_button.bind(on_release=self.open_tip_jar)
        # Contribute
        contribute_button = Button(text="Contribute to the application",font_size=BUTTON_FONT_SIZE,background_color=CONTRIBUTE_COLOR)
        contribute_button.bind(on_release=self.open_code_repository)
        # Widget additions
        button_layout.add_widget(support_button)
        button_layout.add_widget(contribute_button)
        layout.add_widget(title_label)
        layout.add_widget(credit_txt)
        layout.add_widget(button_layout)
        return layout

    def open_code_repository(self, instance):
        urlopen(repo_url)

    def open_tip_jar(self, instance):
        urlopen(tip_url)

    def exit_app(self, instance):
        self.stop()
