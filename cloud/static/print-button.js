/* «Chop etish» tugmasi — huquqiy sahifalarda (rozilik, kuzatuv eslatmasi).
 *
 * `onclick="window.print()"` atributi CSP `script-src` ostida
 * ishlamaydi.  Ikki sahifada bir xil kod bo'lgani uchun alohida fayl:
 * nusxa ko'chirilsa ular vaqt o'tib ajralib ketardi.
 */
document.addEventListener("click", (event) => {
  if (event.target.closest('[data-act="print"]')) window.print();
});
