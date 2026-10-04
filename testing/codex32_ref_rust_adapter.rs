// Small stdin adapter for the pinned, dependency-free Rust reference crate.
// One Codex32 string per line; tab-separated status, data hex, or error.
use codex32::Codex32String;
use std::io::{self, BufRead};

fn main() {
    for line in io::stdin().lock().lines() {
        let encoded = line.expect("stdin");
        let outcome = std::panic::catch_unwind(|| Codex32String::from_string(encoded));
        match outcome {
            Ok(Ok(share)) => {
                let data = share.parts().data();
                let hex: String = data.iter().map(|byte| format!("{byte:02x}")).collect();
                println!("OK\t{hex}");
            }
            Ok(Err(error)) => println!("ERR\t{error:?}"),
            Err(_) => println!("PANIC\tparser panicked"),
        }
    }
}
