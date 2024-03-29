import os
import shutil
from pathlib import Path
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.screenmanager import ScreenManager
from kivy.uix.dropdown import DropDown
from kivy.resources import resource_add_path
from util import (
    get_program_cfg,
    get_app_cfg,
    get_img_file,
    unconfigured_vars,
    store_daily_visualization,
    new_entry_valid,
    overwrite_last_entry,
)
from classes import PageTitle, PopPrompt, BaseScreen, OneButtonPopup
from cfg import ConfigureScreen
from measure import ProgramMeasurementScreen
from about import AboutScreen


ProgramCFG = get_program_cfg()
MCFG = get_app_cfg("main")
MBUTTONS = MCFG["buttons"]
DROPDOWN = MCFG["dropdown"]
ABOUT = MCFG["about"]


class VariableButton(Button):
    def __init__(self, dropdown, app, **kwargs):
        super(VariableButton, self).__init__(**kwargs)
        self.dropdown = dropdown
        self.size_hint_y, self.height = None, DROPDOWN["height"]
        self.font_size = DROPDOWN["font_size"]
        self.background_color = DROPDOWN["color"]
        self.italic = True
        self.app = app
        self.bind(on_release=self.configure_variable)

    def configure_variable(self, instance):
        cfg_screen_name = f"cfg_{self.text}"
        self.app.screen_manager.add_widget(
            ConfigureScreen(name=cfg_screen_name, app=self.app, var=self.text)
        )
        self.app.switch_screen(cfg_screen_name)
        self.dropdown.dismiss()


class VarsDropDown(DropDown):
    def __init__(self, app, vars, **kwargs):
        super(VarsDropDown, self).__init__(**kwargs)
        for v in vars:
            Vbtn = VariableButton(self, app, text=v)
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
        self.source = str(get_img_file())
        self.fit_mode = "fill"

    def reload_img(self):
        self.source = str(get_img_file())
        self.reload()


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
        self.app.switch_screen("about")

    def show_cfg_wheel(self, instance):
        vars = list(ProgramCFG.keys())
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
        self.app.switch_screen("measure")

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


class MainScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super(MainScreen, self).__init__(**kwargs)
        self.app = app
        store_daily_visualization()
        self.main_page_layout = MainPageLayout(self.app)
        self.add_widget(self.main_page_layout)


class MyApp(App):
    def __init__(self):
        super(MyApp, self).__init__()
        self.setup_local_data()
        self.setup_application_screens()

    def setup_local_data(self):
        self.dat_dir = os.path.join(self.user_data_dir, "data")
        os.makedirs(self.dat_dir, exist_ok=True)
        src_dir = os.path.abspath("data")
        for fcp in os.listdir(src_dir):
            src_file, dst_file = os.path.join(src_dir, fcp), os.path.join(
                self.dat_dir, fcp
            )
            if not os.path.exists(dst_file):
                shutil.copy(src_file, dst_file)
        resource_add_path(self.dat_dir)

    def setup_application_screens(self):
        self.main_screen = MainScreen(name="main", app=self)
        self.about_screen = AboutScreen(name="about", app=self)
        self.measure_screen = ProgramMeasurementScreen(name="measure", app=self)

    def build(self):
        self.screen_manager = ScreenManager()
        self.screen_manager.add_widget(self.main_screen)
        self.screen_manager.add_widget(self.about_screen)
        self.screen_manager.add_widget(self.measure_screen)
        self.screen_manager.current = "main"
        return self.screen_manager

    def switch_screen(self, screen_name):
        if screen_name == "main":
            self.screen_manager.transition.direction = "right"
            self.main_screen.main_page_layout.linegraph.reload_img()
        self.screen_manager.transition.direction = "left"
        self.screen_manager.current = screen_name


if __name__ == "__main__":
    MyApp().run()
