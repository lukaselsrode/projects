import os
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.dropdown import DropDown
from classes import PageTitle, PopPrompt
from about import About
from cfg import ConfigureApplication
from measure import ProgramMeasurementApp
from util import new_entry_valid, overwrite_last_entry, load_cfg

CFG = load_cfg()
MCFG = CFG["main"]
PATHS = CFG["paths"]
BUTTONS = MCFG["buttons"]
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
        self.size_hint = BUTTONS["size"]
        self.font_size = BUTTONS["font_size"]


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
        self.size_hint = BUTTONS["layout_size"]

        self.about_button = Button(
            text="About",
            size_hint=ABOUT["size"],
            background_color=ABOUT["color"],
            italic=True,
        )
        self.about_button.bind(on_release=self.get_about_page)

        self.configure_button = MainButton(
            text="Configure", background_color=BUTTONS["cfg_color"]
        )
        self.configure_button.bind(on_press=self.show_cfg_wheel)

        self.measure_button = MainButton(
            text="Measure", background_color=BUTTONS['measure_color']
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
        self.start_measurement() if new_entry_valid() else self.confirm_overwrite()

    def start_measurement(self):
        self.app.close()
        Measure = ProgramMeasurementApp()
        Measure.run()
        self.app.run()

    def confirm_overwrite(self):
        self.popup = PopPrompt(
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
        self.app_title = PageTitle(text="Total Behavioral Tracker")
        self.linegraph, self.main_buttons = MainLineGraph(), MainButtonLayout(self.app)
        self.add_widget(self.app_title)
        self.add_widget(self.linegraph)
        self.add_widget(self.main_buttons)


class MainApp(App):
    def close(self):
        self.root.clear_widgets()
        self.stop()

    def build(self):
        return MainPageLayout(self)


if __name__ == "__main__":
    MainApp().run()