"""Rigwise — redesigned Windows PC control center."""
import os, subprocess, threading, webbrowser, shutil
import customtkinter as ctk
from tkinter import messagebox
import rigwise_core as core

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")
GREEN="#34d399"; NAV="#0f172a"; BG="#0b1020"; PANEL=("#ffffff","#151e31")
TEXT=("#172033","#edf2fb"); MUTED=("#5d6a80","#9aa8bf")

class Rigwise(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Rigwise | PC Control Center")
        self.geometry("1200x780"); self.minsize(980,650); self.configure(fg_color=BG)
        self.specs=None; self.tweaks=[]; self.page="Dashboard"; self.search=ctk.StringVar()
        self.meter=core.Meter(); self.theme="Dark"; self.nav={}
        self.grid_columnconfigure(1,weight=1); self.grid_rowconfigure(0,weight=1)
        self._shell(); self.show("Dashboard")
        threading.Thread(target=self._load,daemon=True).start()
        self.after(1000,self._tick)

    def _shell(self):
        side=ctk.CTkFrame(self,width=215,corner_radius=0,fg_color=NAV)
        side.grid(row=0,column=0,sticky="nsew"); side.grid_propagate(False)
        brand=ctk.CTkFrame(side,fg_color="transparent"); brand.pack(fill="x",padx=18,pady=(25,28))
        ctk.CTkLabel(brand,text="R",width=42,height=42,corner_radius=12,fg_color=GREEN,text_color="#062016",font=ctk.CTkFont(size=24,weight="bold")).pack(side="left")
        ctk.CTkLabel(brand,text="RIGWISE\nPC CONTROL CENTER",justify="left",text_color="#edf2fb",font=ctk.CTkFont(size=14,weight="bold")).pack(side="left",padx=10)
        ctk.CTkLabel(side,text="WORKSPACE",text_color="#71809a",font=ctk.CTkFont(size=10,weight="bold"),anchor="w").pack(fill="x",padx=20,pady=(0,8))
        for name,icon in [("Dashboard","⌂"),("Optimize","✦"),("Startup apps","◷"),("Tools","⚒"),("About","ⓘ")]:
            b=ctk.CTkButton(side,text=f"{icon}    {name}",anchor="w",height=42,corner_radius=10,fg_color="transparent",hover_color="#1e2d43",text_color="#c6d1e2",command=lambda n=name:self.show(n))
            b.pack(fill="x",padx=11,pady=3);self.nav[name]=b
        ctk.CTkFrame(side,fg_color="transparent").pack(fill="both",expand=True)
        ctk.CTkLabel(side,text="●  Local-first tools",text_color=GREEN,anchor="w").pack(fill="x",padx=20,pady=(0,5))
        ctk.CTkLabel(side,text="Review changes before applying",text_color="#71809a",font=ctk.CTkFont(size=10)).pack(anchor="w",padx=20,pady=(0,22))
        main=ctk.CTkFrame(self,fg_color=BG,corner_radius=0);main.grid(row=0,column=1,sticky="nsew")
        main.grid_columnconfigure(0,weight=1);main.grid_rowconfigure(1,weight=1)
        top=ctk.CTkFrame(main,fg_color="transparent");top.grid(row=0,column=0,sticky="ew",padx=28,pady=(20,8));top.grid_columnconfigure(0,weight=1)
        self.heading=ctk.CTkLabel(top,text="Dashboard",font=ctk.CTkFont(size=26,weight="bold"),text_color="#f1f5fb")
        self.heading.grid(row=0,column=0,sticky="w")
        ctk.CTkButton(top,text="Refresh",width=88,height=34,command=self.refresh).grid(row=0,column=1,padx=(0,8))
        ctk.CTkButton(top,text="☼ / ◐",width=70,height=34,command=self.toggle_theme).grid(row=0,column=2)
        self.body=ctk.CTkFrame(main,fg_color="transparent");self.body.grid(row=1,column=0,sticky="nsew",padx=28,pady=8);self.body.grid_columnconfigure(0,weight=1)
        self.status=ctk.StringVar(value="Detecting hardware…")
        foot=ctk.CTkFrame(main,fg_color="#10182a",corner_radius=0);foot.grid(row=2,column=0,sticky="ew")
        ctk.CTkLabel(foot,textvariable=self.status,text_color="#a7b5ca",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=16,pady=7)

    def card(self,parent,title,desc=None):
        c=ctk.CTkFrame(parent,fg_color=PANEL,corner_radius=15,border_width=1,border_color=("#e4eaf2","#243149"))
        if title: ctk.CTkLabel(c,text=title,text_color=TEXT,font=ctk.CTkFont(size=14,weight="bold")).pack(anchor="w",padx=17,pady=(15,0))
        if desc: ctk.CTkLabel(c,text=desc,text_color=MUTED,font=ctk.CTkFont(size=11),wraplength=750,justify="left").pack(anchor="w",padx=17,pady=(4,0))
        return c

    def clear(self):
        for w in self.body.winfo_children():w.destroy()
        f=ctk.CTkScrollableFrame(self.body,fg_color="transparent",corner_radius=0)
        f.grid(row=0,column=0,sticky="nsew");f.grid_columnconfigure(0,weight=1);return f

    def show(self,name):
        self.page=name;self.heading.configure(text=name)
        for n,b in self.nav.items():b.configure(fg_color="#1e2d43" if n==name else "transparent",text_color="#ffffff" if n==name else "#c6d1e2")
        {"Dashboard":self.dashboard,"Optimize":self.optimize,"Startup apps":self.startup,"Tools":self.tools,"About":self.about}[name]()

    def _load(self):
        try:s=core.read_specs();self.after(0,lambda:self._ready(s))
        except Exception as e:self.after(0,lambda:self.status.set(f"Hardware scan failed: {e}"))

    def _ready(self,s):
        self.specs=s;self.tweaks=core.build_tweaks(s) if core.IS_WIN else []
        self.status.set("Hardware detected. Check recommendations before applying changes.")
        self.show(self.page)

    def _tick(self):
        if self.page=="Dashboard" and hasattr(self,"meters"):
            try:
                cpu=self.meter.cpu();ram,total=self.meter.ram()
                vals=[cpu,ram]
                for i,v in enumerate(vals):
                    self.meters[i][0].set(max(0,min(1,v/100)));self.meters[i][1].configure(text=f"{v:.0f}%")
                d=shutil.disk_usage(os.environ.get("SystemDrive","C:")+"\\")
                pct=d.used/d.total
                self.meters[2][0].set(pct);self.meters[2][1].configure(text=f"{pct*100:.0f}%")
                self.meters[2][2].configure(text=f"{d.free/2**30:.1f} GB free")
            except Exception:pass
        self.after(1500,self._tick)

    def dashboard(self):
        p=self.clear()
        hero=ctk.CTkFrame(p,fg_color="#12302f",corner_radius=17);hero.grid(row=0,column=0,sticky="ew",pady=(0,14));hero.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(hero,text="Your PC, at a glance",font=ctk.CTkFont(size=23,weight="bold"),text_color="#edfff7").grid(row=0,column=0,sticky="w",padx=20,pady=(18,3))
        ctk.CTkLabel(hero,text="Understand your hardware, tune carefully, and keep control of every change.",text_color="#b5d9cf").grid(row=1,column=0,sticky="w",padx=20,pady=(0,18))
        ctk.CTkButton(hero,text="Review optimizations  →",command=lambda:self.show("Optimize"),fg_color=GREEN,text_color="#052016",hover_color="#6ee7b7").grid(row=0,column=1,rowspan=2,padx=20)
        row=ctk.CTkFrame(p,fg_color="transparent");row.grid(row=1,column=0,sticky="ew",pady=(0,14))
        for i in range(3):row.grid_columnconfigure(i,weight=1)
        self.meters=[]
        for i,(name,detail) in enumerate([("CPU usage","Processor load"),("Memory usage","RAM in use"),("System drive","Storage used")]):
            c=self.card(row,name,detail);c.grid(row=0,column=i,sticky="ew",padx=(0,8) if i<2 else (0,0))
            v=ctk.CTkLabel(c,text="—",font=ctk.CTkFont(size=28,weight="bold"),text_color=TEXT);v.pack(anchor="w",padx=17,pady=(12,2))
            bar=ctk.CTkProgressBar(c,height=8,progress_color=GREEN);bar.pack(fill="x",padx=17,pady=5);bar.set(0)
            d=ctk.CTkLabel(c,text="Loading…",text_color=MUTED,font=ctk.CTkFont(size=10));d.pack(anchor="w",padx=17,pady=(0,14))
            self.meters.append((bar,v,d))
        low=ctk.CTkFrame(p,fg_color="transparent");low.grid(row=2,column=0,sticky="ew");low.grid_columnconfigure(0,weight=3);low.grid_columnconfigure(1,weight=2)
        c=self.card(low,"Hardware profile","Detected from Windows system information");c.grid(row=0,column=0,sticky="nsew",padx=(0,8))
        if not self.specs:ctk.CTkLabel(c,text="Reading processor, graphics, memory and storage…",text_color=MUTED).pack(anchor="w",padx=17,pady=18)
        else:
            s=self.specs;rows=[("CPU",s["cpu"]),("Graphics",", ".join(g[0] for g in s["gpus"]) or "Not detected"),("Memory",f'{s["ram_gb"]} GB RAM'),("Storage",", ".join(d[0] for d in s["disks"]) or "Not detected"),("Windows",s["os"])]
            for k,v in rows:
                line=ctk.CTkFrame(c,fg_color="transparent");line.pack(fill="x",padx=17,pady=5)
                ctk.CTkLabel(line,text=k,width=95,anchor="w",text_color=MUTED).pack(side="left")
                ctk.CTkLabel(line,text=v,anchor="w",text_color=TEXT,wraplength=400,justify="left").pack(side="left",fill="x",expand=True)
            ctk.CTkFrame(c,fg_color="transparent",height=8).pack()
        q=self.card(low,"Quick actions","Useful Windows shortcuts");q.grid(row=0,column=1,sticky="nsew",padx=(8,0))
        for label,cmd in [("Open Task Manager",self.taskmgr),("Manage startup apps",lambda:self.show("Startup apps")),("Maintenance tools",lambda:self.show("Tools"))]:
            ctk.CTkButton(q,text=label+"   →",anchor="w",height=38,fg_color=("#f0f4f9","#202c40"),text_color=TEXT,command=cmd).pack(fill="x",padx=15,pady=(12,0))
        ctk.CTkFrame(q,fg_color="transparent",height=10).pack()

    def optimize(self):
        p=self.clear();intro=self.card(p,"Optimization library","Search settings, review recommendations, and undo backed-up changes.");intro.grid(row=0,column=0,sticky="ew",pady=(0,10))
        bar=ctk.CTkFrame(intro,fg_color="transparent");bar.pack(fill="x",padx=15,pady=12)
        self.search=ctk.StringVar()
        entry=ctk.CTkEntry(bar,textvariable=self.search,placeholder_text="Search optimizations…",height=36);entry.pack(side="left",fill="x",expand=True,padx=(0,8));entry.bind("<KeyRelease>",lambda e:self._tweak_rows())
        ctk.CTkButton(bar,text="Apply recommended",height=36,command=self.apply_recommended).pack(side="left",padx=(0,7))
        ctk.CTkButton(bar,text="Undo all",height=36,fg_color="#572534",hover_color="#713044",command=self.undo_all).pack(side="left")
        self.tweak_rows=ctk.CTkFrame(p,fg_color="transparent");self.tweak_rows.grid(row=1,column=0,sticky="ew");self.tweak_rows.grid_columnconfigure(0,weight=1)
        self._tweak_rows()
        if not core.IS_WIN:ctk.CTkLabel(self.tweak_rows,text="Tuning controls work only on Windows.",text_color="#fbbf24").grid(row=0,column=0,pady=20)

    def _tweak_rows(self):
        if not hasattr(self,"tweak_rows"):return
        for w in self.tweak_rows.winfo_children():w.destroy()
        query=self.search.get().lower().strip()
        if not self.tweaks:
            ctk.CTkLabel(self.tweak_rows,text="Waiting for hardware detection…",text_color=MUTED).grid(row=0,column=0,pady=15);return
        for i,t in enumerate(self.tweaks):
            if query and query not in (t.name+" "+t.desc+" "+t.reason).lower():continue
            c=self.card(self.tweak_rows,"");c.grid(row=i,column=0,sticky="ew",pady=4)
            line=ctk.CTkFrame(c,fg_color="transparent");line.pack(fill="x",padx=15,pady=12)
            left=ctk.CTkFrame(line,fg_color="transparent");left.pack(side="left",fill="x",expand=True)
            top=ctk.CTkFrame(left,fg_color="transparent");top.pack(anchor="w")
            ctk.CTkLabel(top,text=t.name,text_color=TEXT,font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
            if t.recommended:ctk.CTkLabel(top,text="  RECOMMENDED",text_color=GREEN,font=ctk.CTkFont(size=9,weight="bold")).pack(side="left")
            ctk.CTkLabel(left,text=t.desc,text_color=MUTED,wraplength=700,justify="left").pack(anchor="w",pady=(4,0))
            if t.reason:ctk.CTkLabel(left,text=t.reason,text_color="#60a5fa",wraplength=700,justify="left",font=ctk.CTkFont(size=10)).pack(anchor="w",pady=(3,0))
            if t.kind=="toggle":
                sw=ctk.CTkSwitch(line,text="",width=44,command=lambda t=t:self.toggle_tweak(t));sw.pack(side="right",padx=8)
                try:
                    if t.is_on():sw.select()
                except Exception:pass
            else:ctk.CTkButton(line,text=t.label,width=105,command=lambda t=t:self.run_action(t)).pack(side="right",padx=8)

    def toggle_tweak(self,t):
        try:
            if t.admin and not core.is_admin():
                if messagebox.askyesno("Administrator needed","Restart Rigwise as administrator to change this setting?"):core.relaunch_admin()
                self.show("Optimize");return
            if t.is_on():
                if messagebox.askyesno("Restore previous setting",f"Restore the saved value for {t.name}?"):t.revert()
            else:
                if messagebox.askyesno("Apply tweak",f"{t.name}\n\n{t.desc}\n\nRigwise saves the previous value first. Continue?"):t.apply()
            self.status.set(f"Updated {t.name}. A restart may be required.")
        except Exception as e:messagebox.showerror("Setting change failed",str(e))
        self._tweak_rows()

    def apply_recommended(self):
        todo=[t for t in self.tweaks if t.kind=="toggle" and t.recommended and not t.is_on()]
        if not todo:messagebox.showinfo("Rigwise","Recommended tweaks are already enabled.");return
        names="\n".join("• "+t.name for t in todo)
        if not messagebox.askyesno("Confirm changes","Apply these backed-up settings?\n\n"+names):return
        if any(t.admin for t in todo) and not core.is_admin():
            if messagebox.askyesno("Administrator needed","Some changes need admin rights. Restart Rigwise as administrator?"):core.relaunch_admin()
            return
        failed=[]
        for t in todo:
            try:t.apply()
            except Exception:failed.append(t.name)
        self.status.set(f"Applied {len(todo)-len(failed)} recommended tweak(s).")
        if failed:messagebox.showwarning("Some changes failed","Could not apply:\n"+"\n".join(failed))
        self._tweak_rows()

    def undo_all(self):
        if not messagebox.askyesno("Undo all","Restore all backed-up settings changed by Rigwise? Cleanup actions cannot be undone."):return
        saved=core.load_backup();count=0
        for t in self.tweaks:
            if t.kind=="toggle" and t.key in saved:
                try:t.revert();count+=1
                except Exception:pass
        self.status.set(f"Restored {count} setting(s).");self._tweak_rows()

    def startup(self):
        p=self.clear();c=self.card(p,"Startup applications","Disable auto-start for apps you do not need immediately. This does not uninstall them.");c.grid(row=0,column=0,sticky="ew",pady=(0,10))
        ctk.CTkButton(c,text="Refresh list",command=lambda:self.show("Startup apps")).pack(anchor="e",padx=15,pady=12)
        rows=ctk.CTkFrame(p,fg_color="transparent");rows.grid(row=1,column=0,sticky="ew");rows.grid_columnconfigure(0,weight=1)
        if not core.IS_WIN:ctk.CTkLabel(rows,text="Startup management works only on Windows.",text_color="#fbbf24").grid(row=0,column=0,pady=20);return
        items=core.startup_items()
        if not items:ctk.CTkLabel(rows,text="No startup entries found in the standard registry locations.",text_color=MUTED).grid(row=0,column=0,pady=20)
        for i,(h,name,cmd,on) in enumerate(items):
            c=self.card(rows,"");c.grid(row=i,column=0,sticky="ew",pady=4)
            line=ctk.CTkFrame(c,fg_color="transparent");line.pack(fill="x",padx=15,pady=10)
            left=ctk.CTkFrame(line,fg_color="transparent");left.pack(side="left",fill="x",expand=True)
            ctk.CTkLabel(left,text=name,text_color=TEXT,font=ctk.CTkFont(size=12,weight="bold")).pack(anchor="w")
            ctk.CTkLabel(left,text=cmd[:160],text_color=MUTED,wraplength=700,justify="left",font=ctk.CTkFont(size=10)).pack(anchor="w",pady=(3,0))
            if any(x in name.lower() for x in core.PROTECTED):ctk.CTkLabel(line,text="Protected",text_color=GREEN).pack(side="right")
            else:
                sw=ctk.CTkSwitch(line,text="Enabled",command=lambda hh=h,nn=name:self.flip_startup(hh,nn));sw.pack(side="right",padx=8)
                if on:sw.select()
                else:sw.deselect()

    def flip_startup(self,h,name):
        try:
            now=next((on for hh,n,cmd,on in core.startup_items() if hh==h and n==name),True)
            core.set_startup(h,name,not now);self.status.set(f"Startup preference updated for {name}.")
        except Exception as e:messagebox.showerror("Could not update startup setting",str(e))
        self.show("Startup apps")

    def tools(self):
        p=self.clear();intro=self.card(p,"Maintenance & diagnostics","Manual utilities—choose each action yourself. Windows may require administrator rights.");intro.grid(row=0,column=0,sticky="ew",pady=(0,10))
        grid=ctk.CTkFrame(p,fg_color="transparent");grid.grid(row=1,column=0,sticky="ew")
        for i in range(2):grid.grid_columnconfigure(i,weight=1)
        tools=[
            ("Temporary cleanup","Remove unused files from Temp folders; files in use are skipped.","Clean temporary files",self.clean_temp),
            ("Flush DNS cache","Useful when a site or game server has stale network lookups.","Flush DNS",self.flush_dns),
            ("Network report","View IP, gateway and DNS information.","Run diagnostics",self.network_report),
            ("Battery health report","Generate a Windows battery report on supported laptops.","Create report",self.battery_report),
            ("Task Manager","Inspect processes and resource usage.","Open Task Manager",self.taskmgr),
            ("Windows Update","Open official update settings.","Open settings",self.open_updates),
            ("System Information","Open the built-in hardware/system report.","Open msinfo32",self.open_msinfo),
            ("Rigwise backups","Open the folder with saved original settings.","Open folder",self.open_backup)]
        for i,(title,desc,label,fn) in enumerate(tools):
            c=self.card(grid,title,desc);c.grid(row=i//2,column=i%2,sticky="nsew",padx=(0,7) if i%2==0 else (7,0),pady=5)
            ctk.CTkButton(c,text=label,command=fn,height=34).pack(anchor="w",padx=15,pady=(13,15))

    def clean_temp(self):
        if messagebox.askyesno("Temporary cleanup","Delete temporary files that are not currently in use?"):self._async("Temporary cleanup",core.clean_temp)

    def _async(self,title,fn):
        self.status.set(f"Running {title}…")
        def work():
            try:r=fn();self.after(0,lambda:messagebox.showinfo(title,str(r)));self.after(0,lambda:self.status.set(str(r)))
            except Exception as e:self.after(0,lambda:messagebox.showerror(title,str(e)))
        threading.Thread(target=work,daemon=True).start()

    def flush_dns(self):
        if not core.IS_WIN:return messagebox.showinfo("Flush DNS","Available on Windows.")
        self._async("Flush DNS",lambda:core.run(["ipconfig","/flushdns"]) or "No confirmation returned. Try administrator mode.")

    def network_report(self):
        if not core.IS_WIN:return messagebox.showinfo("Network report","Available on Windows.")
        self._show_text("Network diagnostics",core.run(["ipconfig","/all"],timeout=25) or "No output returned.")

    def battery_report(self):
        if not core.IS_WIN:return messagebox.showinfo("Battery report","Available on Windows.")
        path=os.path.join(os.path.expanduser("~"),"Desktop","battery-report.html")
        core.run(["powercfg","/batteryreport","/output",path],timeout=30)
        if os.path.exists(path):webbrowser.open("file:///"+path.replace("\\","/"));messagebox.showinfo("Battery report",f"Saved to {path}")
        else:messagebox.showwarning("Battery report","Windows could not create a report. This works only on supported battery devices.")

    def _show_text(self,title,content):
        w=ctk.CTkToplevel(self);w.title(title);w.geometry("780x550")
        box=ctk.CTkTextbox(w,wrap="none");box.pack(fill="both",expand=True,padx=12,pady=12);box.insert("1.0",content);box.configure(state="disabled")
        ctk.CTkButton(w,text="Close",command=w.destroy).pack(anchor="e",padx=12,pady=(0,12))

    def taskmgr(self):
        if core.IS_WIN:subprocess.Popen(["taskmgr.exe"])
        else:messagebox.showinfo("Task Manager","Available on Windows.")

    def open_updates(self):
        if core.IS_WIN:os.startfile("ms-settings:windowsupdate")
        else:webbrowser.open("https://support.microsoft.com/windows")

    def open_msinfo(self):
        if core.IS_WIN:subprocess.Popen(["msinfo32.exe"])
        else:messagebox.showinfo("System Information","Available on Windows.")

    def open_backup(self):
        os.makedirs(core.APPDATA,exist_ok=True)
        if core.IS_WIN:os.startfile(core.APPDATA)
        else:webbrowser.open("file://"+core.APPDATA)

    def about(self):
        p=self.clear();c=self.card(p,"About Rigwise","A practical control center for understanding and maintaining your Windows PC.");c.grid(row=0,column=0,sticky="ew",pady=(0,10))
        ctk.CTkLabel(c,text="Clarity • Reversible settings • User control",text_color=GREEN,font=ctk.CTkFont(size=15,weight="bold")).pack(anchor="w",padx=17,pady=(18,7))
        ctk.CTkLabel(c,text="Hardware checks run locally. Registry tweaks save original values before changing them. Some options need administrator permission or a restart. Results vary by PC—no tweak can guarantee more FPS.",text_color=MUTED,wraplength=800,justify="left").pack(anchor="w",padx=17,pady=(0,18))
        for title,desc in [("Undo changes","Use Optimize → Undo all to restore settings Rigwise backed up."),("Be selective","Laptop power settings can reduce battery life, and visual or mouse settings are personal preferences."),("Privacy","Rigwise does not require an account or upload your hardware report.")]:
            x=self.card(p,title,desc);x.pack(fill="x",pady=5)

    def refresh(self):
        if self.page=="Dashboard":
            self.status.set("Refreshing hardware scan…");threading.Thread(target=self._load,daemon=True).start()
        else:self.show(self.page)

    def toggle_theme(self):
        self.theme="Light" if self.theme=="Dark" else "Dark";ctk.set_appearance_mode(self.theme);self.show(self.page);self.status.set(f"Appearance: {self.theme.lower()} mode.")

if __name__=="__main__":
    try:Rigwise().mainloop()
    except Exception as e:
        try:messagebox.showerror("Rigwise could not start",str(e))
        except Exception:pass
        raise
