from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

class HyperlinkLabel(Label):
    def __init__(self, **kwargs):
        super(HyperlinkLabel, self).__init__(**kwargs)
        self.markup = True

    def on_ref_press(self, ref):
        print(f"Clicked on {ref}")

class MyApp(App):
    def build(self):
        layout = BoxLayout(orientation='vertical')
        title_label = Label(text='My Kivy App', font_size='20sp')
        hyperlink_text = HyperlinkLabel(text='[ref=http://example.com]Example 1[/ref]\n[ref=http://example.com]Example 2[/ref]')
        layout.add_widget(title_label)
        layout.add_widget(hyperlink_text)
        return layout

if __name__ == '__main__':
    MyApp().run()
