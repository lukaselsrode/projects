from kivy.uix.textinput import TextInput
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from util import ConfigCFG, load_variable_data, update_var_key_data
from classes import ExitButton, PageTitle, TwoButtonLayout, PopPrompt, BaseScreen

GRID_LAYOUT = ConfigCFG["layout"]
TEXT = ConfigCFG["text"]


class ConfigureVarKeyView(GridLayout):
    def __init__(self, file, var, data, configurer, app, **kwargs):
        super(ConfigureVarKeyView, self).__init__(**kwargs)
        self.app, self.var, self.data, self.file, self.configurer = (
            app,
            var,
            data,
            file,
            configurer,
        )
        self.cols, self.padding, self.spacing = GRID_LAYOUT
        self.exit = ExitButton(application=self.app)
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
        self.configurer.next_screen()

    def accept_input(self, instance):
        self.user_input_keys = [
            x.lower() for x in self.config_input.text.split("\n") if x
        ]
        if not self.user_input_keys and not self.data["user"]:
            self.user_input_keys = self.data["default"]
        self.confirm_new_config()


class ConfigureScreen(BaseScreen):
    def __init__(self, app, var, **kwargs):
        self.app = app
        super(ConfigureScreen, self).__init__(**kwargs)
        self.cfg_var = var
        self.data = load_variable_data(self.cfg_var)
        self.vars_list = list(self.data.keys())
        self.current_var_index = 0
        self.add_widget(self.current_cfg_view())

    def current_cfg_view(self):
        var = self.vars_list[self.current_var_index]
        return ConfigureVarKeyView(self.cfg_var, var, self.data[var], self, self.app)

    def next_screen(self):
        self.current_var_index += 1
        if not self.current_var_index < len(self.vars_list):
            self.app.switch_screen("main")
        else:
            self.clear_widgets()
            self.add_widget(self.current_cfg_view())
