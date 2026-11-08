EDIT THE CHARACTER IN: Documents\NAB Mascot\sajeeb  (Settings > Character > Open character folder). The folder inside the app is only the original copy.
If a new NAB version brings new pictures, your old folder is saved as Documents\NAB Mascot\backup_<date> and the new set is copied in.

Pictures: .webp (PNG converted to WEBP is fine), transparent background, feet at the bottom edge, all drawn at the SAME scale
(the app does not resize one picture relative to another). Facing right for walk / run / climb (it flips for the other direction).

Animation sets (frames of one pose are listed in sajeeb_poses.json under "frames"):
  jump_1..7    crouch, take-off, rising, apex, tucked fall, landing, recover - chosen by speed up/down
  dance_1..7   time based (7 fps)       celebrate_1..4 (after a save)     wave_1..2     phone_1..2
  sleep_1..2   breathing while asleep
Single poses: sit (idle), point, lounge, sitbox, back_view, paws, laptop, umbrella, wink, happy, react, surprised, panic,
  tea, tea2, heart_hug, angry, sad, love, shy, thinking, peek, closeup
Pictures marked "bust" in the json get a soft fade at the bottom (head-and-shoulders pictures).
To use one image for a set, delete its "frames" and "fps" lines in sajeeb_poses.json.
Idle poses picked at random: sit, phone, laptop, tea, paws, wink, sitbox, umbrella, thinking, react.

Walk (walk_4), run (run_3) and climb (back_view) are single pictures that the app bobs and tilts like Riko. The pictures face LEFT, so "left": true is set for them in sajeeb_poses.json (the app flips them when he walks right).
