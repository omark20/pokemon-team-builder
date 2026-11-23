// A counter response for the team Charizard, Blastoise, Venusaur, as the backend's
// counter core (backend/app/domain/counter.py) answers it. counterFixture.json is
// that answer, unedited: every Pokémon carries the four moves the core gives it from
// its captured move list in samples/, the baselines are taken over the 18 default
// Pokémon whose move lists are captured, and the candidates are limited to Gyarados,
// Pikachu and Dragonite so the three picks end in a win, a loss and a draw. None of
// the three hits Venusaur for 2×, so that rule is waived for Dragonite's pick.
import type { CounterResult } from "../types";
import answer from "./counterFixture.json";

export const COUNTER = answer as CounterResult;
