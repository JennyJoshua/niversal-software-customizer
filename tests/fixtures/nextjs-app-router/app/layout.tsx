/* USC:branding:metadata:start */
export const metadata = {
  title: "Fixture Product",
  description: "Fixture description",
};
/* USC:branding:metadata:end */

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
