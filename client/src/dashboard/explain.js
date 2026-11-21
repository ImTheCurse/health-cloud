// "Learn more" text for each chart: what the measurement is, how the watch gets
// it, and which way is usually better. General information only; every dialog
// ends with a not-medical-advice line added by the card.

const what = (text) => ({ heading: "What it is", text });
const how = (text) => ({ heading: "How it's measured", text });
const better = (text) => ({ heading: "What's better", text });

export const EXPLAIN = {
  heartRate: {
    title: "Heart rate",
    sections: [
      what("How many times your heart beats per minute, sampled through the day and night."),
      how("An optical sensor on the back of the watch reads blood flow at the wrist. Readings during hard, jerky movement are the least accurate."),
      better("There is no single good number: it should rise with effort and fall back afterwards. What matters is the pattern — a day that runs higher than usual at rest can mean stress, illness, alcohol, heat or poor sleep."),
    ],
  },
  resting: {
    title: "Resting heart rate",
    sections: [
      what("Your heart rate when fully at rest, estimated once a day mostly from sleep and still periods."),
      how("Google derives it from the day's heart-rate samples; it is not a single moment's reading."),
      better("Lower is usually better. Typical adults sit around 60–100 bpm, and fit people often lower. A rise of several beats above your own norm for a few days often comes with illness, overtraining or poor recovery."),
    ],
  },
  timeInZone: {
    title: "Time in heart-rate zone",
    sections: [
      what("Minutes spent in each heart-rate zone: light, moderate, vigorous and peak, from easiest to hardest."),
      how("Each heart-rate sample is placed in a zone using the limits Google sets from your age and resting heart rate, shown on the Heart tab."),
      better("Most people benefit from plenty of light and moderate time and a smaller share of vigorous and peak. Health guidelines commonly suggest at least 150 minutes of moderate, or 75 of vigorous, activity a week."),
    ],
  },
  zones: {
    title: "Heart-rate zones",
    sections: [
      what("The heart-rate limits that define each zone for you."),
      how("Google calculates them from your age and resting heart rate, and updates them as those change."),
      better("Neither higher nor lower limits are better; they describe you. They shift as your resting heart rate changes."),
    ],
  },
  variability: {
    title: "Heart-rate variability",
    sections: [
      what("HRV is how much the time between heartbeats varies. A healthy heart does not beat like a metronome."),
      how("Measured from beat-to-beat intervals, mostly while you are still or asleep, in milliseconds."),
      better("Higher HRV is usually a sign of better recovery and health. It varies a lot between people, so compare against your own average, not anyone else's. A drop below your usual range often follows hard training, stress, alcohol or illness."),
    ],
  },
  nightlyHrv: {
    title: "Nightly heart-rate variability",
    sections: [
      what("Google's nightly HRV summary: the average over the night, and the value in deep sleep (RMSSD)."),
      how("Calculated from beat-to-beat intervals during sleep, when movement does not disturb the reading."),
      better("Higher is usually better, against your own baseline. Several nights below your norm can mean you need more recovery."),
    ],
  },
  nonRemHeartRate: {
    title: "Non-REM heart rate",
    sections: [
      what("Your average heart rate during non-REM (light and deep) sleep."),
      how("Taken from heart-rate samples in the non-REM stages of the night."),
      better("Lower is usually better and reflects good recovery. A night noticeably higher than your norm often follows alcohol, a late meal, illness or a hard day."),
    ],
  },
  entropy: {
    title: "HRV entropy",
    sections: [
      what("A measure of how irregular, or complex, your beat-to-beat pattern is over the night."),
      how("Google computes it from the same overnight beat intervals as HRV."),
      better("Higher complexity is generally associated with a healthier, more adaptable system, but this is a research-grade measure: watch your own trend rather than the number."),
    ],
  },
  sleep: {
    title: "Sleep",
    sections: [
      what("Time asleep each night, split into deep, light and REM sleep, plus time awake in bed."),
      how("The watch infers sleep stages from movement and heart-rate patterns. It is a good estimate, not a sleep-lab measurement."),
      better("Most adults do best with 7–9 hours. Typically about 10–25% is deep sleep and 20–25% REM; most of the rest is light. Short awakenings are normal."),
    ],
  },
  sleepStages: {
    title: "Sleep stages",
    sections: [
      what("The stages you moved through during one sleep: awake, REM, light and deep."),
      how("Inferred from movement and heart rate, in short intervals through the night."),
      better("A healthy night cycles through the stages several times, with more deep sleep early and more REM towards morning."),
    ],
  },
  sleepTiming: {
    title: "Sleep timing",
    sections: [
      what("When your main sleep started and ended each night."),
      how("Taken from the start and end of each night's main sleep session."),
      better("Consistency is better: going to bed and waking at similar times every day, weekends included, supports sleep quality and daytime energy."),
    ],
  },
  temperature: {
    title: "Skin temperature",
    sections: [
      what("How your skin temperature during sleep differs from your own baseline."),
      how("A sensor on the watch reads wrist skin temperature overnight; Google compares it with your recent nights."),
      better("Small changes are normal. A sustained rise above baseline can come with illness, alcohol, a warm room or the menstrual cycle; it is a signal to notice, not a diagnosis."),
    ],
  },
  breathingNight: {
    title: "Breathing rate in sleep",
    sections: [
      what("Breaths per minute during sleep, overall and in each sleep stage."),
      how("Estimated from small rhythmic changes in heart rate and blood flow that follow breathing."),
      better("Most adults breathe about 12–20 times a minute at rest. Your own rate is usually very steady; a jump above your norm can come with illness."),
    ],
  },
  oxygen: {
    title: "Blood oxygen",
    sections: [
      what("SpO₂: the percentage of your blood's haemoglobin carrying oxygen."),
      how("Read optically with red and infrared light, mostly during sleep when you are still."),
      better("Higher is better; 95–100% is typical for healthy adults at sea level. Brief dips in sleep happen. Repeated drops below about 90% are worth raising with a doctor."),
    ],
  },
  oxygenNightly: {
    title: "Nightly blood oxygen",
    sections: [
      what("Google's nightly SpO₂ average, with its lower and upper bounds."),
      how("Summarised from the night's SpO₂ readings."),
      better("Higher and steadier is better; 95–100% is typical. Frequent low nights can point to disturbed breathing in sleep."),
    ],
  },
  breathing: {
    title: "Breathing rate",
    sections: [
      what("Your average breaths per minute, one figure per day."),
      how("Estimated overnight from heart-rate and blood-flow rhythms."),
      better("About 12–20 breaths per minute is typical at rest. Look for changes from your own steady rate rather than the absolute number."),
    ],
  },
  steps: {
    title: "Steps",
    sections: [
      what("Steps counted by the watch."),
      how("An accelerometer detects the rhythm of walking and running. Arm-heavy movement can add or miss a few."),
      better("More is generally better. Research links roughly 7,000–10,000 steps a day with lower health risks for most adults, with benefits starting well below that."),
    ],
  },
  distance: {
    title: "Distance",
    sections: [
      what("How far you moved on foot."),
      how("Estimated from steps and your stride length, or from GPS during a tracked exercise."),
      better("More is generally better, built up gradually."),
    ],
  },
  floors: {
    title: "Floors",
    sections: [
      what("Floors climbed: about three metres of elevation gained on foot counts as one."),
      how("A barometric sensor detects the change in air pressure as you climb."),
      better("More is better; climbing is good, short, vigorous exercise."),
    ],
  },
  activityLevel: {
    title: "Activity level",
    sections: [
      what("Minutes spent sedentary, lightly active, moderately active and very active."),
      how("Classified from movement intensity through the day."),
      better("Less sedentary time and more active time is better. Even light activity that breaks up long sitting helps."),
    ],
  },
  azm: {
    title: "Active Zone Minutes",
    sections: [
      what("Google's count of minutes at elevated heart rate: fat burn counts once, cardio and peak count double."),
      how("Calculated from your heart rate against your personal zones."),
      better("More is better. The common target is 150 Active Zone Minutes a week, matching health guidelines for moderate exercise."),
    ],
  },
  sedentary: {
    title: "Sitting still",
    sections: [
      what("Periods long enough for the watch to count as sedentary: sitting or lying still while awake."),
      how("Detected from a lack of movement, outside sleep."),
      better("Less is better. Long unbroken sitting is a health risk of its own, even for active people; standing or walking for a few minutes each hour helps."),
    ],
  },
  exercise: {
    title: "Exercise sessions",
    sections: [
      what("Each tracked or auto-detected exercise session. A bigger dot was a harder session."),
      how("Dot size is Google's Active Zone Minutes for the session, or, where it sent none, minutes in each heart-rate zone weighted 1 (light) to 4 (peak) — a common way to estimate training load."),
      better("Regular sessions spread through the week are better than occasional very hard ones. Big sessions need recovery days around them."),
    ],
  },
  exerciseMinutes: {
    title: "Minutes of exercise",
    sections: [
      what("Total time in exercise sessions each day."),
      how("The sum of each day's sessions' durations."),
      better("Guidelines suggest at least 150 minutes of moderate exercise a week, spread over most days."),
    ],
  },
  exerciseTimeline: {
    title: "Sessions across the day",
    sections: [
      what("When each session happened during the day."),
      how("From each session's start and end time."),
      better("Any time that suits you is fine; consistency matters more than the hour."),
    ],
  },
  pace: {
    title: "Pace",
    sections: [
      what("Average minutes per kilometre for each run; the line is the mean of your last few runs."),
      how("Distance from GPS or stride length, divided into the run's moving time."),
      better("Faster (lower) is better for the same kind of run. Compare like with like: easy runs should be slower than hard ones."),
    ],
  },
  weeklyDistance: {
    title: "Weekly distance",
    sections: [
      what("Kilometres run each week, with the week's longest run marked."),
      how("Run distances added up Monday to Sunday."),
      better("Steady, gradual growth is better than big jumps. Many coaches advise raising weekly distance by no more than about 10% a week to limit injury risk."),
    ],
  },
  efficiency: {
    title: "Aerobic efficiency",
    sections: [
      what("Pace against average heart rate for each run."),
      how("Each dot is one run: pace across, heart rate up."),
      better("Running faster at the same heart rate, or at the same pace with a lower heart rate, means your aerobic fitness is improving. Heat, hills and fatigue push dots the wrong way."),
    ],
  },
  intensity: {
    title: "Intensity by week",
    sections: [
      what("The share of each week's running time spent in each heart-rate zone."),
      how("From the minutes each run spent in each zone."),
      better("Many endurance plans keep about 80% of running easy (light and moderate) and 20% hard. Mostly-hard weeks raise injury and burnout risk."),
    ],
  },
  energy: {
    title: "Energy eaten",
    sections: [
      what("Calories logged as food each day."),
      how("Only what you log in an app that syncs to Google Health."),
      better("Depends on your goal; matching intake to energy used maintains weight."),
    ],
  },
  water: {
    title: "Water",
    sections: [
      what("Water logged each day."),
      how("Only what you log."),
      better("Needs vary with size, heat and exercise; a common guide is about 2–3 litres a day from all drinks and food."),
    ],
  },
  vo2: {
    title: "VO₂ max",
    sections: [
      what("An estimate of the most oxygen your body can use during hard exercise, in ml per kg per minute: the standard measure of cardio fitness."),
      how("Estimated from your heart rate, pace and personal details, not measured directly."),
      better("Higher is better, and it is one of the strongest predictors of long-term health. It falls with age and rises with regular hard aerobic exercise."),
    ],
  },
  runVo2: {
    title: "Run VO₂ max",
    sections: [
      what("VO₂ max estimated specifically from your runs."),
      how("From the relationship between pace and heart rate in outdoor runs with GPS."),
      better("Higher is better; it rises as running fitness improves."),
    ],
  },
  height: {
    title: "Height",
    sections: [
      what("Your height as last recorded."),
      how("Entered by you in a connected app."),
      better("Used to estimate stride length and calories; keep it accurate."),
    ],
  },
};

// What a day outside your personal range usually means, per chart, and whether
// that side is the good one or the one to watch. Shown when hovering a marked
// point. "Often" and "can", never a diagnosis.
const good = (text) => ({ tone: "good", text });
const watch = (text) => ({ tone: "watch", text });

export const PERSONAL = {
  heartRate: {
    above: watch("A day running higher than usual often comes with illness starting, stress, poor sleep, heat, caffeine or alcohol."),
    below: good("A calmer day than usual: often a sign of rest and good recovery."),
  },
  resting: {
    above: watch("A resting heart rate above your norm often comes before or with illness, and also follows poor sleep, alcohol, dehydration, stress or overtraining."),
    below: good("Lower than usual is usually good: often better fitness or a well-recovered body."),
  },
  variability: {
    above: good("Higher HRV than usual is usually a sign of good recovery and low stress."),
    below: watch("Lower HRV than usual often means incomplete recovery: hard training, poor sleep, alcohol, stress or illness."),
  },
  nightlyHrv: {
    above: good("A night with higher HRV than usual: usually good recovery and a relaxed nervous system."),
    below: watch("A night with lower HRV than usual often follows hard training, alcohol, a late meal, stress or illness starting."),
  },
  nonRemHeartRate: {
    above: watch("A higher sleeping heart rate than usual often follows alcohol, a late meal, a warm room, stress or illness."),
    below: good("A lower sleeping heart rate than usual: usually a restful, well-recovered night."),
  },
  oxygen: {
    above: good("Higher oxygen saturation than usual: nothing to watch."),
    below: watch("Lower than usual can come with disturbed breathing in sleep, a cold or chest infection, altitude, or a poor sensor fit."),
  },
  oxygenNightly: {
    above: good("A night with higher oxygen saturation than usual: nothing to watch."),
    below: watch("A night lower than usual can mean disturbed breathing in sleep, a cold or chest infection, altitude, or a loose watch."),
  },
  breathing: {
    above: watch("Breathing faster than usual in sleep is one of the earliest signs of illness, and also follows hard exercise, alcohol or a warm room."),
    below: good("Slower than usual is usually fine: often a deeper, calmer night."),
  },
};
