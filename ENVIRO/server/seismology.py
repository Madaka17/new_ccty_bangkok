"""
Earthquake formulas shared by the simulator, the situation page and the AI brief: magnitude from a station's
PGA, PGA at a distance, PGA <-> MMI, the felt radius, and the magnitude that gives a wanted MMI. Moved out of
simulator.py (Oct 2026).
"""
import math


PEAK_SHAKE_CONST = 0.68  # calibrated to this simulator's own _sample() envelope, not a published GMPE

# Separate calibration for the reference-location MMI prediction pathway
# (pga_at_distance/predict_mmi/solve_magnitude_for_mmi below), deliberately
# decoupled from `pga_calibration` (the admin-configurable STA/LTA
# trigger-sensitivity knob) -- that constant is tuned for near-station
# detection, not absolute real-world PGA. This one is chosen so realistic
# (magnitude, distance) pairs land in a realistic PGA/MMI range for public
# communication: e.g. M7 at ~10km predicts ~400 Gal / MMI ~VIII, and M8
# near-source predicts ~1300 Gal / MMI ~X -- both consistent with typical
# real near-source ground motions for events of that size.
MMI_PGA_SCALE = 40.0


def magnitude_amp_multiplier(magnitude):
    """Rough, clearly-approximate scaling: not a real ground-motion prediction
    equation (GMPE) -- just enough spread that picking a bigger magnitude in
    the simulator produces a visibly bigger PGA and a higher alert level."""
    return 10 ** ((magnitude - 4.8) / 2.0)


def estimate_magnitude(pga_gal, dist_km, pga_calibration):
    """Inverts magnitude_amp_multiplier() + the _sample() attenuation curve to
    recover an estimated magnitude from an observed PGA at a known distance.
    This is the exact algebraic inverse of *this simulator's own* synthetic
    physics (not a real published attenuation relation) -- but it plays the
    same role a real single/few-station magnitude estimator does: turn a
    local ground-motion reading + distance into a magnitude, in real time,
    before waiting for a human or a slower network-wide solution."""
    atten = 1.0 / (1.0 + dist_km / 55.0)
    denom = pga_calibration * PEAK_SHAKE_CONST * atten
    if pga_gal <= 0 or denom <= 0:
        return 0.0
    return round(4.8 + 2.0 * math.log10(pga_gal / denom), 2)


def pga_at_distance(magnitude, dist_km, depth_km):
    """PGA (Gal) at an arbitrary point (not just a station), using the same
    magnitude-scaling and attenuation *shape* as _sample()'s envelope, but
    scaled by MMI_PGA_SCALE (not the near-field `pga_calibration` knob) so
    the result lands in a realistic absolute PGA range for the GMICE below to
    convert. Hypocentral distance (surface distance + depth, combined in
    quadrature) so a shallow-but-close event and a deep-but-directly-below
    one attenuate consistently."""
    hypo_km = math.sqrt(dist_km ** 2 + depth_km ** 2)
    atten = 1.0 / (1.0 + hypo_km / 55.0)
    return MMI_PGA_SCALE * atten * magnitude_amp_multiplier(magnitude)


def pga_to_mmi(pga_gal):
    """Real, published PGA -> Modified Mercalli Intensity conversion (a
    GMICE): Wald, Quitoriano, Heaton & Kanamori (1999), 'Relationships
    between Peak Ground Acceleration, Peak Ground Velocity, and Modified
    Mercalli Intensity in California', Earthquake Spectra 15(3). Their
    piecewise PGA fit (as also documented in USGS ShakeMap's GMICE
    reference): a shallower slope below the MMI~4.22 crossover, a steeper
    one above it. This is a real, cited formula -- the PGA fed into it is
    still this simulator's own synthetic value, not a real ground recording."""
    if pga_gal <= 0:
        return 1.0
    low = 2.20 * math.log10(pga_gal) + 1.00
    high = 3.66 * math.log10(pga_gal) - 1.66
    mmi = low if low <= 4.22 else high
    return max(1.0, min(12.0, mmi))


def mmi_to_pga(mmi):
    """Algebraic inverse of pga_to_mmi(), used to solve 'what PGA would give
    this predicted intensity' (e.g. for the reference-level PGA bands shown
    on the warning ladder, or for solving backwards for a target magnitude)."""
    mmi = max(1.0, min(12.0, mmi))
    if mmi <= 4.22:
        return 10 ** ((mmi - 1.00) / 2.20)
    return 10 ** ((mmi + 1.66) / 3.66)


FELT_MMI_THRESHOLD = 2.0  # below this, treated as "not felt" -- same cutoff the frontend's ripple uses


def felt_radius_km(magnitude, depth_km):
    """Distance at which shaking fades below FELT_MMI_THRESHOLD -- the
    algebraic inverse of pga_at_distance(), solved for distance instead of
    PGA. Exact server-side counterpart of frontend/index.html's
    feltRadiusKm() (kept in sync deliberately: both derive "how far/how long
    is this event still felt" from the same physics), used here to decide
    when an event should stop being reported as "currently happening" --
    see get_situation()'s staleness check in routes/situation.py."""
    amp_mult = magnitude_amp_multiplier(magnitude)
    target_pga = mmi_to_pga(FELT_MMI_THRESHOLD)
    atten = target_pga / (MMI_PGA_SCALE * amp_mult)
    if atten <= 0 or atten >= 1:
        return 3000.0  # fallback ceiling, same as the frontend's
    hypo_km = 55 * (1 / atten - 1)
    return min(3000.0, max(50.0, math.sqrt(max(0.0, hypo_km ** 2 - depth_km ** 2))))


MMI_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def mmi_roman(mmi):
    # floor, not round: the `levels` table's mmi_min/mmi_max bands are integer
    # boundaries (e.g. Lv.3 is [5.0, 6.0)), so a value like 5.71 must still
    # display as "V" to match the level it was actually classified into --
    # rounding it to "VI" would show a numeral one band higher than the level.
    return MMI_ROMAN[max(0, min(11, int(mmi) - 1))]


def predict_mmi(magnitude, dist_km, depth_km):
    """Predicted Modified Mercalli Intensity at a given point: this
    simulator's own synthetic attenuation model (pga_at_distance) feeding a
    real, cited GMICE (pga_to_mmi/Wald et al. 1999). This is what drives the
    alert *level* now -- see REFERENCE_STATION and server/db.py LEVELS."""
    return round(pga_to_mmi(pga_at_distance(magnitude, dist_km, depth_km)), 2)


def solve_magnitude_for_mmi(target_mmi, dist_km, depth_km, cap=9.5):
    """Inverts predict_mmi(): the magnitude that would produce `target_mmi` at
    a point `dist_km`/`depth_km` away, given this simulator's own physics.
    Used by the admin 'trigger a specific alert level' control so a demo
    quake is internally consistent (real distance + real depth + a magnitude
    solved to match) instead of a magnitude picked by guesswork.

    `cap` defaults to 9.5 -- the largest earthquake ever instrumentally
    recorded (1960 Valdivia, Chile, Mw 9.5) -- as an honest ceiling: for a
    point far enough from the reference location, even this maximum
    real-world magnitude may not reach the requested target_mmi, and the
    default behavior is to return whatever the ceiling actually produces
    there rather than a fabricated number (the caller should report the
    shortfall, not claim the target was hit).

    A caller MAY explicitly raise `cap` past 9.5 for a deliberate stress-test
    scenario -- e.g. verifying the Level 6 continuous-siren-until-acknowledged
    UI actually fires -- where hitting the target level matters more than
    real-world plausibility. Any such caller must make that tradeoff visible
    to the end user (event place name / UI copy), since past ~9.5 the
    magnitude is no longer physically real; see `historical_event ==
    "andaman_l6"` in server/routes/admin.py for exactly this case."""
    target_pga = mmi_to_pga(target_mmi)
    hypo_km = math.sqrt(dist_km ** 2 + depth_km ** 2)
    atten = 1.0 / (1.0 + hypo_km / 55.0)
    denom = MMI_PGA_SCALE * atten
    if target_pga <= 0 or denom <= 0:
        return 4.8
    magnitude = 4.8 + 2.0 * math.log10(target_pga / denom)
    return round(max(3.0, min(cap, magnitude)), 2)
