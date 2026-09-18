//! Heat-pump sizing.
//!
//! Waste heat leaves a data center at a temperature set by its cooling system.
//! If that is already hotter than the sink needs, the heat can be used
//! directly; otherwise a heat pump has to lift it, and the electricity that
//! costs is what makes a match more or less worthwhile.

use crate::types::{Cooling, SinkCat};

/// Temperature the waste heat is available at, °C.
pub fn supply_temp_c(cooling: Cooling) -> f32 {
    match cooling {
        Cooling::Air => 35.0,
        Cooling::RearDoor => 42.0,
        Cooling::Liquid => 55.0,
        // Nearly every real site: assume the least useful case.
        Cooling::Unknown => 35.0,
    }
}

/// Temperature the sink's heating system needs, °C.
pub fn required_temp_c(cat: SinkCat) -> f32 {
    match cat {
        SinkCat::Pool => 32.0,
        SinkCat::Wwtp => 35.0,
        SinkCat::Greenhouse => 40.0,
        SinkCat::Brewery => 50.0,
        SinkCat::Hotel => 60.0,
        SinkCat::ResidentialMultifamily => 60.0,
        SinkCat::School => 70.0,
        SinkCat::Hospital => 75.0,
        SinkCat::University => 75.0,
        SinkCat::Office => 75.0,
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct HeatPump {
    pub required: bool,
    /// Units of heat delivered per unit of electricity. Infinite when no heat
    /// pump is needed, so `delivered / cop` is correctly zero electricity.
    pub cop: f32,
}

/// Size the heat pump needed to move heat from `cooling` to `cat`.
///
/// The temperature lift includes `approach_c` twice over: the heat exchanger
/// cannot reach the source temperature exactly, so the evaporator sees
/// `supply - approach` while the condenser must reach `required`.
///
/// The reference example (air-cooled to a hospital, COP ≈ 0.5 * 348.15 / 45
/// ≈ 3.87) divides by the full 45 K lift including the approach.
pub fn heat_pump(
    cooling: Cooling,
    cat: SinkCat,
    approach_c: f32,
    carnot_fraction: f32,
) -> HeatPump {
    let supply = supply_temp_c(cooling);
    let required = required_temp_c(cat);
    let lift = required - supply + approach_c;

    if lift <= 0.0 {
        return HeatPump {
            required: false,
            cop: f32::INFINITY,
        };
    }
    let th = required + 273.15;
    HeatPump {
        required: true,
        cop: carnot_fraction * th / lift,
    }
}
