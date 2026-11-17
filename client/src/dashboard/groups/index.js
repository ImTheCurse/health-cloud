import Activity from "./Activity.jsx";
import Breathing from "./Breathing.jsx";
import Exercise from "./Exercise.jsx";
import FoodBody from "./FoodBody.jsx";
import Heart from "./Heart.jsx";
import Sleep from "./Sleep.jsx";

/**
 * The dashboard's tabs. `bucketed` marks a tab with a route that takes a bucket
 * size, which is the only kind the hourly / daily switch changes.
 */
export const GROUPS = [
  { id: "heart", label: "Heart", Component: Heart, bucketed: true },
  { id: "sleep", label: "Sleep", Component: Sleep, bucketed: false },
  { id: "breathing", label: "Breathing & oxygen", Component: Breathing, bucketed: true },
  { id: "activity", label: "Activity", Component: Activity, bucketed: true },
  { id: "exercise", label: "Exercise", Component: Exercise, bucketed: false },
  { id: "food", label: "Food & body", Component: FoodBody, bucketed: false },
];

export const GROUP_IDS = GROUPS.map((group) => group.id);
