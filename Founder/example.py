# -*- coding: utf-8 -*-
"""نمونه: وضعیت صفحه را تشخیص بده. اول ریموت XBOX باید باز باشد."""
from founder import Remote, Screen

remote = Remote("XBOX")
scr = Screen(remote)

with scr.frozen():
    print("متن بالای صفحه:", scr.read(0, 0, 1280, 80, single_line=False))
    m = scr.find_text("Transfer")
    print("Transfer:", m)
    for line in scr.read_all(0, 0, 1280, 720):
        print(f"  ({line.x:4},{line.y:4})  {line.text}")
scr.save("last_frame.png")
