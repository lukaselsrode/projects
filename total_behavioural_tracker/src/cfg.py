from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput
from classes import ExitButton, PageTitle, PopPrompt, TwoButtonLayout
from util import update_var_key_data, load_variable_data,load_cfg



CFG = load_cfg()["cfg"]
GRID_LAYOUT = CFG["layout"]
TEXT = CFG["text"]



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
            font_size=CFG["input"]["font_size"],
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
        display_txt = self.data["default"] if not self.data["user"] else self.data["user"]
        self.config_input.text = "\n".join(display_txt).lower()

    def confirm_new_config(self):
        self.popup = PopPrompt(
            title=f"Confirm {self.var} configuration",
            prompt=f"Confirm {self.var} configuration for your {self.file.rstrip('.yaml')}?",
            yfunc=self.write_new_config,
            nfunc=self.cancel_popup,
        )

    def cancel_popup(self, instance):
        if self.popup: self.popup.dismiss()

    def write_new_config(self, instance):
        update_var_key_data(self.file, self.var, self.user_input_keys)
        self.popup.dismiss()
        self.app.next_screen()
        

    def accept_input(self, instance):
        self.user_input_keys = [x.lower() for x in self.config_input.text.split("\n") if x]
        if not self.user_input_keys and not self.data["user"]:
            self.user_input_keys = self.data["default"]
        self.confirm_new_config()


class ConfigureApplication(App):
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
        if self.current_var_index < len(self.vars_list):
            self.root.clear_widgets()
            self.root.add_widget(self.current_cfg_view())
        else:
            self.stop()
