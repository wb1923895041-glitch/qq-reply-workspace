import secrets
import tkinter as tk
from tkinter import messagebox
import winreg
root=tk.Tk();root.title('QQ 连接令牌');root.geometry('560x220')
tk.Label(root,text='生成或输入 OneBot 连接令牌，再复制到 QQ 客户端的反向 WebSocket 配置。',wraplength=520).pack(pady=15)
value=tk.StringVar(value=secrets.token_urlsafe(32));entry=tk.Entry(root,textvariable=value,width=60);entry.pack(pady=6)
def save():
    token=value.get().strip()
    if len(token)<24 or not token.isascii() or any(c.isspace() for c in token):
        messagebox.showerror('无效令牌','令牌须为至少 24 位、不含空格的 ASCII 字符。');return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment',0,winreg.KEY_SET_VALUE) as key: winreg.SetValueEx(key,'QQ_ONEBOT_TOKEN',0,winreg.REG_SZ,token)
    root.clipboard_clear();root.clipboard_append(token)
    messagebox.showinfo('设置完成','令牌已保存到当前用户环境变量，并复制到剪贴板。请粘贴到 OneBot 客户端配置。')
tk.Button(root,text='保存并复制',command=save,padx=20,pady=5).pack(pady=14)
root.mainloop()
