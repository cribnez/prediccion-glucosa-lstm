import os
import csv
import time
from dataclasses import dataclass, asdict
from typing import Optional
import tkinter as tk
from tkinter import messagebox, filedialog

# === THEME / BRANDING ===
PRIMARY_BG = "#0E2A47"
CARD_BG    = "#103255"
ACCENT     = "#39B54A"
TEXT_CLR   = "#F2F6FA"
MUTED_TXT  = "#B8C7D9"
BTN_BG     = "#2FA043"
BTN_TXT    = "#FFFFFF"
BTN_SEC_BG = "#1F6FB2"
BTN_SEC_TX = "#EAF2FA"
FONT_FAMILY= "Segoe UI"
WINDOW_SIZE= "900x520"
APP_TITLE  = "Predicción de Glucosa - Interfaz"


@dataclass
class PacienteInput:
    nombre: str
    glucosa_post: float
    insulina_u: float
    kcal: float
    peso: float
    altura: float
    edad: float
    timestamp: float

    @property
    def imc(self) -> Optional[float]:
        try:
            m = self.altura / 100.0
            return round(self.peso / (m * m), 2) if m > 0 else None
        except Exception:
            return None


class GlucosaUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.configure(bg=PRIMARY_BG)
        self.root.geometry(WINDOW_SIZE)

        self.var_nombre  = tk.StringVar()
        self.var_glucosa = tk.StringVar()
        self.var_ins     = tk.StringVar()
        self.var_kcal    = tk.StringVar()
        self.var_peso    = tk.StringVar()
        self.var_altura  = tk.StringVar()
        self.var_edad    = tk.StringVar()
        self.result_var  = tk.StringVar(value="Predicción: — mg/dL")
        self.imc_var     = tk.StringVar(value="IMC: —")

        self._build_header()
        self._build_form()
        self._build_actions()
        self._build_footer()

    def _build_header(self):
        wrapper = tk.Frame(self.root, bg=PRIMARY_BG)
        wrapper.pack(side=tk.TOP, fill=tk.X, pady=(10, 6))
        tk.Label(wrapper, text="Predicción de Glucosa (30 min)",
                 bg=PRIMARY_BG, fg=ACCENT, font=(FONT_FAMILY, 24, "bold")).pack()
        tk.Label(wrapper, text="Ingresa los datos del paciente:",
                 bg=PRIMARY_BG, fg=MUTED_TXT, font=(FONT_FAMILY, 11)).pack()

    def _build_form(self):
        form = tk.Frame(self.root, bg=CARD_BG)
        form.pack(padx=20, pady=8, fill=tk.X)

        tk.Label(form, text="Nombre del paciente:", bg=CARD_BG, fg=TEXT_CLR,
                 font=(FONT_FAMILY, 11)).grid(row=0, column=0, sticky="w", padx=(12, 8), pady=8)
        e_nombre = tk.Entry(form, textvariable=self.var_nombre, font=(FONT_FAMILY, 11), width=45)
        e_nombre.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=8, columnspan=3)
        e_nombre.insert(0, "Paciente Ejemplo")

        fields = [
            ("Glucosa post-prueba (mg/dL):", self.var_glucosa, "110"),
            ("Insulina bolus (U):",          self.var_ins,     "2"),
            ("Calorías recientes (kcal):",   self.var_kcal,    "240"),
            ("Peso (kg):",                   self.var_peso,    "70"),
            ("Altura (cm):",                 self.var_altura,  "170"),
            ("Edad (años):",                 self.var_edad,    "25"),
        ]
        r_base = 1
        for i, (label, var, ph) in enumerate(fields):
            r = r_base + i // 2
            c = (i % 2) * 2
            tk.Label(form, text=label, bg=CARD_BG, fg=TEXT_CLR,
                     font=(FONT_FAMILY, 10)).grid(row=r, column=c, sticky="w", padx=(12, 8), pady=6)
            entry = tk.Entry(form, textvariable=var, font=(FONT_FAMILY, 10), width=16)
            entry.grid(row=r, column=c+1, sticky="w", padx=(0, 18), pady=6)
            entry.insert(0, ph)

        res = tk.Frame(self.root, bg=PRIMARY_BG)
        res.pack(fill=tk.X, padx=20, pady=(8, 0))
        tk.Label(res, textvariable=self.result_var, bg=PRIMARY_BG, fg=TEXT_CLR,
                 font=(FONT_FAMILY, 14, "bold")).pack(side=tk.LEFT, padx=(0, 20))
        tk.Label(res, textvariable=self.imc_var, bg=PRIMARY_BG, fg=MUTED_TXT,
                 font=(FONT_FAMILY, 12, "italic")).pack(side=tk.LEFT)

        tk.Label(self.root,
                 text="Elaborado por Oscar José María Pedrero de la Cruz",
                 bg=PRIMARY_BG, fg=MUTED_TXT, font=(FONT_FAMILY, 10, "italic")).pack(pady=(8, 0))

    def _build_actions(self):
        btns = tk.Frame(self.root, bg=PRIMARY_BG)
        btns.pack(side=tk.TOP, pady=12)

        tk.Button(btns, text="Predecir (demo)", command=self.on_predict,
                  bg=BTN_BG, fg=BTN_TXT, bd=0, padx=14, pady=8,
                  font=(FONT_FAMILY, 11, "bold")).pack(side=tk.LEFT, padx=6)

        tk.Button(btns, text="Guardar registro", command=self.on_save_csv,
                  bg=BTN_SEC_BG, fg=BTN_SEC_TX, bd=0, padx=14, pady=8,
                  font=(FONT_FAMILY, 11, "bold")).pack(side=tk.LEFT, padx=6)

        tk.Button(btns, text="Limpiar", command=self.on_clear,
                  bg="#2D445C", fg="#F0F6FB", bd=0, padx=14, pady=8,
                  font=(FONT_FAMILY, 11, "bold")).pack(side=tk.LEFT, padx=6)

    def _build_footer(self):
        footer = tk.Frame(self.root, bg=PRIMARY_BG)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=8)
        tk.Label(
            footer,
            text="Elaborado en colaboración con el Dr. Norberto Urbina Brito",
            bg=PRIMARY_BG, fg=MUTED_TXT, font=(FONT_FAMILY, 10)
        ).pack()

    def _parse_inputs(self) -> Optional[PacienteInput]:
        campos = {
            "Nombre del paciente": self.var_nombre.get(),
            "Glucosa post-prueba (mg/dL)": self.var_glucosa.get(),
            "Insulina bolus (U)": self.var_ins.get(),
            "Calorías recientes (kcal)": self.var_kcal.get(),
            "Peso (kg)": self.var_peso.get(),
            "Altura (cm)": self.var_altura.get(),
            "Edad (años)": self.var_edad.get(),
        }
        faltantes = [k for k, v in campos.items() if str(v).strip() == ""]
        if faltantes:
            messagebox.showerror("Campos vacíos", "Completa todos los campos:\n- " + "\n- ".join(faltantes))
            return None
        try:
            return PacienteInput(
                nombre=str(campos["Nombre del paciente"]).strip(),
                glucosa_post=float(campos["Glucosa post-prueba (mg/dL)"]),
                insulina_u=float(campos["Insulina bolus (U)"]),
                kcal=float(campos["Calorías recientes (kcal)"]),
                peso=float(campos["Peso (kg)"]),
                altura=float(campos["Altura (cm)"]),
                edad=float(campos["Edad (años)"]),
                timestamp=time.time()
            )
        except ValueError:
            messagebox.showerror("Error", "Todos los campos numéricos deben contener valores válidos.")
            return None

    def on_predict(self):
        data = self._parse_inputs()
        if not data:
            return
        est_carb = max(data.kcal / 4.0, 0.0)
        pred_mgdl = data.glucosa_post + 0.3 * est_carb - 4.5 * data.insulina_u
        pred_mgdl = max(40.0, min(400.0, pred_mgdl))
        self.result_var.set(f"Predicción a 30 min: {pred_mgdl:.1f} mg/dL")
        self.imc_var.set(f"IMC: {data.imc:.2f}" if data.imc else "IMC: —")

    def on_save_csv(self):
        data = self._parse_inputs()
        if not data:
            return
        path = filedialog.asksaveasfilename(
            title="Guardar registro CSV", defaultextension=".csv", filetypes=[("CSV", "*.csv")]
        )
        if not path:
            return
        is_new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(data).keys()) + ["IMC"])
            if is_new:
                writer.writeheader()
            row = asdict(data)
            row["IMC"] = data.imc
            writer.writerow(row)
        messagebox.showinfo("Guardado", f"Registro guardado en:\n{path}")

    def on_clear(self):
        for var in [self.var_nombre, self.var_glucosa, self.var_ins, self.var_kcal,
                    self.var_peso, self.var_altura, self.var_edad]:
            var.set("")
        self.result_var.set("Predicción: — mg/dL")
        self.imc_var.set("IMC: —")


def main():
    root = tk.Tk()
    GlucosaUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
