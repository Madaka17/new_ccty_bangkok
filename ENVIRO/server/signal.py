"""Real signal-processing primitives run against the (simulated) sensor streams.

These are genuine implementations -- not lookup tables -- so swapping the
synthetic waveform source in `simulator.py` for a real ADC/MQTT feed later
requires no change here.
"""
import numpy as np

SAMPLE_RATE_HZ = 20.0  # samples per second per station/axis


def sta_lta(buffer, sta_sec=1.0, lta_sec=15.0, sample_rate_hz=SAMPLE_RATE_HZ):
    """Classic STA/LTA ratio on the *tail* of a buffer of amplitude samples.

    Returns the ratio at the last sample, or 0 if the buffer is too short
    for a full long-term window yet. `sample_rate_hz` lets this run
    correctly against a buffer sampled slower than the usual 20Hz (e.g. a
    node reporting once/sec instead of streaming raw waveform -- see
    routes/nodes.py node_waveform's low_res fallback) -- unlike frequency-
    domain analysis (fft_spectrum/dominant_frequency), a plain energy
    ratio like this stays meaningful at any sample rate, just coarser.
    """
    arr = np.asarray(buffer, dtype=float)
    sta_n = max(1, int(sta_sec * sample_rate_hz))
    lta_n = max(sta_n + 1, int(lta_sec * sample_rate_hz))
    if len(arr) < lta_n:
        return 0.0
    energy = arr ** 2
    sta = energy[-sta_n:].mean()
    lta = energy[-lta_n:].mean()
    if lta <= 1e-9:
        return 0.0
    return float(sta / lta)


def sta_lta_series(buffer, sta_sec=1.0, lta_sec=15.0, sample_rate_hz=SAMPLE_RATE_HZ):
    """STA/LTA ratio evaluated at every point (for charting), not just the tail."""
    arr = np.asarray(buffer, dtype=float)
    sta_n = max(1, int(sta_sec * sample_rate_hz))
    lta_n = max(sta_n + 1, int(lta_sec * sample_rate_hz))
    energy = arr ** 2
    out = np.zeros(len(arr))
    csum = np.cumsum(energy)

    def windowed_mean(n, i):
        lo = max(0, i - n + 1)
        total = csum[i] - (csum[lo - 1] if lo > 0 else 0.0)
        return total / (i - lo + 1)

    for i in range(len(arr)):
        lta = windowed_mean(lta_n, i)
        sta = windowed_mean(sta_n, i)
        out[i] = (sta / lta) if lta > 1e-9 else 0.0
    return out.tolist()


def fft_spectrum(buffer, max_hz=20.0, bins=40):
    """Real magnitude spectrum via numpy's FFT, binned to `bins` buckets up to max_hz."""
    arr = np.asarray(buffer, dtype=float)
    if len(arr) < 8:
        return [{"f": round(i * max_hz / bins, 2), "a": 0.0} for i in range(bins)]
    windowed = arr * np.hanning(len(arr))
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(arr), d=1.0 / SAMPLE_RATE_HZ)
    out = []
    for i in range(bins):
        f_lo, f_hi = i * max_hz / bins, (i + 1) * max_hz / bins
        mask = (freqs >= f_lo) & (freqs < f_hi)
        amp = float(spectrum[mask].mean()) if mask.any() else 0.0
        out.append({"f": round((f_lo + f_hi) / 2, 2), "a": round(amp, 3)})
    return out


def dominant_frequency(buffer):
    arr = np.asarray(buffer, dtype=float)
    if len(arr) < 8:
        return 0.0
    spectrum = np.abs(np.fft.rfft(arr * np.hanning(len(arr))))
    freqs = np.fft.rfftfreq(len(arr), d=1.0 / SAMPLE_RATE_HZ)
    if len(spectrum) <= 1:
        return 0.0
    idx = int(np.argmax(spectrum[1:]) + 1)  # skip DC bin
    return float(freqs[idx])


def correlation_matrix(buffers_by_station):
    """Pearson correlation between each pair of station buffers (same length window)."""
    names = list(buffers_by_station.keys())
    n = len(names)
    if n == 0:
        return names, []
    min_len = min(len(b) for b in buffers_by_station.values())
    min_len = max(min_len, 2)
    mat = np.array([np.asarray(buffers_by_station[k][-min_len:], dtype=float) for k in names])
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.corrcoef(mat)
    corr = np.nan_to_num(corr, nan=0.0)
    return names, corr.round(3).tolist()


def peak_abs(buffer, n=None):
    arr = np.asarray(buffer, dtype=float)
    if n:
        arr = arr[-n:]
    return float(np.max(np.abs(arr))) if len(arr) else 0.0


def classify_source(buffer, neighbor_buffer=None):
    """Distinguish a real earthquake from a passing vehicle, machinery/
    construction, or background noise using three real, independent signal
    properties -- not a single STA/LTA ratio. The three checks are applied in
    a deliberate order, mirroring how a human analyst would reason about it:

      1. Is anything happening at all? (STA/LTA activity level -- if the
         recent window is no louder than the long-term background, it's
         background noise and the other checks don't matter.)
      2. Frequency content -- specifically how "peaky"/tonal the spectrum is
         (max bin vs. mean bin amplitude). At this simulator's 20 Hz sample
         rate the Nyquist limit is 10 Hz, so a literal "1-10 Hz energy
         fraction" would capture nearly the *entire* available spectrum for
         any signal and discriminate nothing -- peakiness is the feature
         that actually separates them: white background noise is close to
         flat (empirically ~3-6), a real earthquake's broadband multi-Hz
         shaking is moderately peaky (~7-10), and a single rotating-machinery
         tone is sharply peaky (>20).
      3. Network coherence: is the same disturbance seen at a *nearby
         station too*? A real regional seismic wave is; a truck or
         jackhammer next to one sensor is not. This is the strongest
         available discriminator -- but it is only *evidence* when the
         neighbour is actually active. A quake's wave takes real time to
         reach the next station down the line (~3s for 12km at S-wave
         speed): in that gap the neighbour is still reading pure background,
         which means "not yet corroborated", not "confirmed local-only".
         Coherence only counts for or against earthquake once the neighbour
         itself shows elevated activity; until then this per-station read
         falls back on frequency/waveform alone, same as a real single
         sensor would before the network catches up -- and even then,
         broadband local noise (e.g. a vehicle) can look spectrally similar
         to distant shaking, which is exactly why coherence, not frequency
         content, is the fact that should decide it once it's available.

    Returns a dict of category -> percentage (sums to ~100).
    """
    arr = np.asarray(buffer, dtype=float)
    if len(arr) < int(SAMPLE_RATE_HZ * 16):
        return {"earthquake": 15.0, "vehicle": 20.0, "machinery": 20.0, "noise": 45.0}

    activity = sta_lta(list(arr))  # ~1.0 at rest; elevated when something is currently louder than background

    def clip01(x):
        return max(0.0, min(1.0, x))

    # ---- 1. nothing happening -> background noise, frequency/coherence moot ----
    if activity < 1.3:
        return {"earthquake": 4.0, "vehicle": 9.0, "machinery": 9.0, "noise": 78.0}

    # windowed to the last few seconds, not the whole multi-minute buffer -- a
    # short burst (a truck passing, a jackhammer starting, or the ~9s of an
    # earthquake's actual shaking inside a much longer ring buffer) would
    # otherwise be drowned out by however many quiet seconds sit on either
    # side of it, both in the correlation and in the spectrum below
    recent_n = min(len(arr), int(SAMPLE_RATE_HZ * 6))
    activity_boost = clip01((activity - 1.3) / 4.0)  # stronger activity -> more confident either way

    # ---- 2. frequency content: peakiness only (see docstring for why an
    # explicit frequency-band fraction doesn't work at this sample rate) ----
    spectrum = fft_spectrum(list(arr[-recent_n:]))
    amps = np.array([b["a"] for b in spectrum])
    peakiness = float(amps.max()) / (float(amps.mean()) + 1e-9)
    noise_like = clip01((6.0 - peakiness) / 3.0)       # ~1 at peakiness<=3, ~0 by 6
    broadband_like = clip01(1.0 - abs(peakiness - 8.5) / 6.5)  # peaks around 8.5 (measured quake range ~7-10)
    tonal_like = clip01((peakiness - 15.0) / 15.0)     # ~0 below 15, ~1 by 30 (measured machinery ~25+)

    # ---- 3. network coherence, only once the neighbour is itself active ----
    coherence = None  # None = not yet corroborated either way (neighbour still quiet)
    if neighbor_buffer is not None and len(neighbor_buffer) >= int(SAMPLE_RATE_HZ * 16):
        narr = np.asarray(neighbor_buffer, dtype=float)
        neighbor_activity = sta_lta(list(narr))
        if neighbor_activity >= 1.3:
            n = min(len(arr), len(narr), recent_n)
            with np.errstate(invalid="ignore", divide="ignore"):
                c = np.corrcoef(arr[-n:], narr[-n:])[0, 1]
            coherence = 0.0 if np.isnan(c) else float(abs(c))

    eq_base = 0.3 + 2.2 * broadband_like * (0.5 + 0.5 * activity_boost)
    vehicle_base = 0.3 + 1.0 * broadband_like * (0.5 + 0.5 * activity_boost)
    machinery_base = 0.3 + 2.0 * tonal_like * (0.5 + 0.5 * activity_boost)
    noise_base = 0.3 + 1.0 * noise_like

    if coherence is not None and coherence > 0.35:
        # corroborated by an equally-active neighbour -- strong, decisive evidence
        eq_score = eq_base + 3.0 * (coherence - 0.35)
        vehicle_score, machinery_score = vehicle_base * 0.3, machinery_base * 0.3
    elif coherence is not None:
        # actively refuted: neighbour is active too but uncorrelated -> local-only source
        eq_score = eq_base * 0.25
        vehicle_score, machinery_score = vehicle_base + 1.0, machinery_base + 1.0
    else:
        # not yet corroborated either way -- frequency/waveform evidence stands alone
        eq_score = eq_base
        vehicle_score, machinery_score = vehicle_base, machinery_base
    noise_score = noise_base

    raw = {
        "earthquake": max(0.05, eq_score), "vehicle": max(0.05, vehicle_score),
        "machinery": max(0.05, machinery_score), "noise": max(0.05, noise_score),
    }
    total = sum(raw.values())
    return {k: round(v / total * 100, 1) for k, v in raw.items()}
