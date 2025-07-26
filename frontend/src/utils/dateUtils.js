// src/utils/dateUtils.js

/**
 * Checks if the current time is within US stock market regular trading hours.
 * Considers 9:30 AM to 4:00 PM Eastern Time (ET), Monday to Friday.
 * @returns {boolean} True if the market is open, false otherwise.
 */
export const isMarketHours = () => {
  const now = new Date();
  
  // Get the current time in the "America/New_York" timezone
  const etTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));

  const dayOfWeek = etTime.getDay(); // Sunday = 0, Saturday = 6
  const hour = etTime.getHours();
  const minute = etTime.getMinutes();

  // Market is closed on weekends
  if (dayOfWeek === 0 || dayOfWeek === 6) {
    return false;
  }

  // Market is open between 9:30 AM and 4:00 PM ET
  const marketOpen = hour > 9 || (hour === 9 && minute >= 30);
  const marketClosed = hour >= 16;

  return marketOpen && !marketClosed;
}; 