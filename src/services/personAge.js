const AGE_TIME_ZONE = 'Asia/Manila';

function dateParts(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
  if (!match) return null;
  const [, year, month, day] = match.map(Number);
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() + 1 !== month || date.getUTCDate() !== day) return null;
  return { year, month, day };
}

export function manilaTodayIso(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: AGE_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now).reduce((result, part) => ({ ...result, [part.type]: part.value }), {});
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function calculateAge(dateOfBirth, asOfDate = manilaTodayIso()) {
  const birth = dateParts(dateOfBirth);
  const todayValue = asOfDate instanceof Date
    ? (Number.isNaN(asOfDate.getTime()) ? null : manilaTodayIso(asOfDate))
    : asOfDate;
  const today = dateParts(todayValue);
  if (!birth || !today || birth.year > today.year) return null;

  const birthday = birth.month === 2 && birth.day === 29 &&
    !((today.year % 4 === 0 && today.year % 100 !== 0) || today.year % 400 === 0)
    ? { month: 3, day: 1 }
    : birth;
  let age = today.year - birth.year;
  if (today.month < birthday.month || (today.month === birthday.month && today.day < birthday.day)) age -= 1;
  return age >= 0 ? age : null;
}
