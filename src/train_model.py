import os, glob, json, time, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from dateutil import parser as dtparser
from tqdm import tqdm
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from joblib import dump
import matplotlib.pyplot as plt
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

# ======= CONFIGURACIÓN =======
DATA_DIR = r"C:\Users\pedre\Desktop\DIADATA\datasets for T1D"  
OUT_DIR  = "outputs"
EPOCHS = 100
BATCH_SIZE = 256
PAST_MINUTES = 60   # ventana pasada (min)
HORIZON_MIN  = 30   # horizonte futuro (min)
RESAMPLE_EVERY = "5min"  # frecuencia
SEED = 42
SAMPLE_MAX_FILES = None  #none(agarra todos los archivos de DiaData), si se quiere agarrar una parte poner numero 5
# =============================

def _first_match(df, keys):
    keys = [k.lower() for k in keys]
    for c in df.columns:
        lc = c.lower().strip()
        for k in keys:
            if k in lc:
                return c
    return None

def detect_time_col(df): return _first_match(df, ["ts","time","date","timestamp"])
def detect_glucose_col(df): return _first_match(df, ["glucosecgm","glucose","cgm","sensor glucose"])
def detect_insulin_col(df): return _first_match(df, ["insulin","bolus","basal"])
def detect_carb_col(df): return _first_match(df, ["carb","meal","cho"])
def detect_hr_col(df): return _first_match(df, ["heart","hr"])
def detect_steps_col(df): return _first_match(df, ["step","steps"])

def load_one_csv(path):
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    tcol = detect_time_col(df)
    if tcol is None: raise ValueError(f"No time column in {os.path.basename(path)}")
    try:
        t = pd.to_datetime(df[tcol], errors="coerce", utc=False)
        if t.isna().all():
            t = df[tcol].astype(str).map(lambda x: dtparser.parse(x, fuzzy=True) if pd.notna(x) else pd.NaT)
    except Exception:
        t = df[tcol].astype(str).map(lambda x: dtparser.parse(x, fuzzy=True) if pd.notna(x) else pd.NaT)
    df["t"] = pd.to_datetime(t, errors="coerce")
    df = df.dropna(subset=["t"]).sort_values("t")
    glu = detect_glucose_col(df)
    ins = detect_insulin_col(df)
    cho = detect_carb_col(df)
    hr  = detect_hr_col(df)
    stp = detect_steps_col(df)
    out = pd.DataFrame({
        "t": df["t"].values,
        "glucose": df[glu].values if glu else np.nan,
        "insulin": df[ins].values if ins else 0.0,
        "carb":    df[cho].values if cho else 0.0,
        "hr":      df[hr].values  if hr  else 0.0,
        "steps":   df[stp].values if stp else 0.0
    })
    out = out.set_index("t").sort_index()
    out = out.resample(RESAMPLE_EVERY).mean()
    out["glucose"] = out["glucose"].interpolate(limit_direction="both")
    for c in ["insulin","carb","hr","steps"]:
        out[c] = out[c].fillna(method="ffill").fillna(0.0)
    out = out.dropna(subset=["glucose"])
    return out

def load_data_dir(data_dir, sample_max_files=None):
    csvs = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    if not csvs: raise FileNotFoundError(f"No CSV in {data_dir}")
    if sample_max_files is not None: csvs = csvs[:sample_max_files]
    series = []
    print(f"Cargando {len(csvs)} archivos CSV de DiaData...")
    t0 = time.time()
    for f in tqdm(csvs, desc="Archivos"):
        try: series.append(load_one_csv(f))
        except Exception as e: print(f"Omitido {os.path.basename(f)} | {e}")
    print(f"Tiempo de carga: {time.time()-t0:.1f} s")
    if not series: raise RuntimeError("No series válidas.")
    return series

def make_sequences(df, feature_cols, past_steps, future_steps):
    X_list, y_list = [], []
    arr = df[feature_cols].values
    glu_idx = feature_cols.index("glucose")
    for i in range(past_steps, len(arr) - future_steps):
        X_list.append(arr[i-past_steps:i, :])
        y_list.append(arr[i+future_steps, glu_idx])
    return np.array(X_list), np.array(y_list)

def temporal_split(X, y, train_ratio=0.7, val_ratio=0.15):
    n = len(X)
    i1 = int(train_ratio * n)
    i2 = int((train_ratio + val_ratio) * n)
    return X[:i1], y[:i1], X[i1:i2], y[i1:i2], X[i2:], y[i2:]

def build_lstm(input_shape):
    inp = layers.Input(shape=input_shape)
    x = layers.LSTM(64, return_sequences=True)(inp)
    x = layers.Dropout(0.2)(x)
    x = layers.LSTM(32)(x)
    x = layers.Dense(32, activation="relu")(x)
    out = layers.Dense(1, activation="linear")(x)
    model = keras.Model(inp, out)
    model.compile(optimizer=keras.optimizers.Adam(1e-3), loss="mse", metrics=["mae"])
    return model

def invert_glucose_only(scaler, feature_cols, glucose_scaled_vec):
    dummy = np.zeros((len(glucose_scaled_vec), len(feature_cols)))
    dummy[:, feature_cols.index("glucose")] = glucose_scaled_vec.reshape(-1)
    inv = scaler.inverse_transform(dummy)
    return inv[:, feature_cols.index("glucose")]

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    tf.random.set_seed(SEED)
    np.random.seed(SEED)
    features = ["glucose","insulin","carb","hr","steps"]
    past_steps = max(1, PAST_MINUTES // 5)
    future_steps = max(1, HORIZON_MIN // 5)
    series_raw = load_data_dir(DATA_DIR, sample_max_files=SAMPLE_MAX_FILES)
    all_raw = pd.concat(series_raw, axis=0).sort_index()
    scaler_global = MinMaxScaler()
    scaler_global.fit(all_raw[features].values)
    series_scaled = []
    for df in series_raw:
        vals = scaler_global.transform(df[features].values)
        series_scaled.append(pd.DataFrame(vals, index=df.index, columns=features))
    all_scaled = pd.concat(series_scaled, axis=0).sort_index()
    X, y = make_sequences(all_scaled, features, past_steps, future_steps)
    if len(y) < 100: raise RuntimeError("Pocos ejemplos.")
    X_tr, y_tr, X_val, y_val, X_te, y_te = temporal_split(X, y)
    model = build_lstm(X_tr.shape[1:])
    callbacks = [
        keras.callbacks.EarlyStopping(patience=8, restore_best_weights=True, monitor="val_loss"),
        keras.callbacks.ReduceLROnPlateau(patience=4, factor=0.5)
    ]
    print("Entrenando...")
    hist = model.fit(X_tr, y_tr, validation_data=(X_val, y_val), epochs=EPOCHS, batch_size=BATCH_SIZE, callbacks=callbacks, verbose=1)
    print("Evaluando...")
    yhat_te = model.predict(X_te, verbose=0).reshape(-1,1)
    y_pred = invert_glucose_only(scaler_global, features, yhat_te)
    y_true = invert_glucose_only(scaler_global, features, y_te.reshape(-1,1))
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(mean_squared_error(y_true, y_pred, squared=False))
    r2 = float(r2_score(y_true, y_pred))
    print(f"MAE = {mae:.2f} mg/dL | RMSE = {rmse:.2f} mg/dL | R² = {r2:.3f}")
    model_path = os.path.join(OUT_DIR, "glucose_lstm_30min.keras")
    scaler_path = os.path.join(OUT_DIR, "minmax_scaler_global.joblib")
    model.save(model_path)
    dump({"scaler": scaler_global, "features": features}, scaler_path)
    report = {
        "timestamp": pd.Timestamp.utcnow().isoformat(),
        "data_dir": DATA_DIR,
        "epochs": EPOCHS,
        "batch_size": BATCH_SIZE,
        "past_minutes": PAST_MINUTES,
        "horizon_minutes": HORIZON_MIN,
        "examples_train": int(len(y_tr)),
        "examples_val": int(len(y_val)),
        "examples_test": int(len(y_te)),
        "test_mae_mgdl": mae,
        "test_rmse_mgdl": rmse,
        "test_r2": r2,
        "model_path": model_path,
        "scaler_path": scaler_path
    }
    with open(os.path.join(OUT_DIR, "training_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    plt.figure(figsize=(9,4))
    plt.plot(hist.history["loss"], label="MSE train")
    plt.plot(hist.history["val_loss"], label="MSE val")
    plt.title("Entrenamiento - Pérdida (MSE)")
    plt.xlabel("Época")
    plt.ylabel("MSE")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "loss_curves.png"), dpi=130)
    plt.close()
    take = min(288, len(y_true))
    plt.figure(figsize=(10,4))
    plt.plot(y_true[:take], label="Glucosa real")
    plt.plot(y_pred[:take], label="Glucosa predicha")
    plt.title("Predicción de glucosa - ventana de prueba")
    plt.xlabel("Muestras (cada 5 min)")
    plt.ylabel("mg/dL")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "pred_vs_true.png"), dpi=130)
    plt.close()
    print(f"Modelo: {model_path}")
    print(f"Scaler: {scaler_path}")
    print("Listo")

if __name__ == "__main__":
    main()
