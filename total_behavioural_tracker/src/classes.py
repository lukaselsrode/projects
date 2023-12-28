from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import  Screen
from kivy.app import App
from util import ClassesCFG

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
        self.app.switch_screen('main')


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


class BaseScreen(Screen):
    def __init__(self, **kwargs):
        super(BaseScreen, self).__init__(**kwargs)
