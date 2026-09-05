#let doc = json("resume.json")
#let p = doc.profile
#let roles = doc.at("roles", default: ())
#let projects = doc.at("projects", default: ())
#let education = doc.at("education", default: ())
#let skill-groups = doc.at("skill_groups", default: ())

#set page(paper: "us-letter", margin: (x: 0.65in, y: 0.5in))
#set text(font: "Libertinus Serif", size: 10pt, fill: rgb("#111111"), hyphenate: false)
#set par(justify: false, leading: 0.58em, spacing: 0.58em)
#set list(tight: false, indent: 0.85em, body-indent: 0.4em, spacing: 0.52em, marker: [•])
#show link: set text(fill: rgb("#111111"))

#let rule() = line(length: 100%, stroke: 0.55pt + rgb("#111111"))

// A section title never sits alone at the foot of a page: sticky keeps it
// with whatever follows, and breakable: false keeps title and rule together.
#let section(title) = block(
  breakable: false,
  sticky: true,
  above: 1.5em,
  below: 0.7em,
)[
  #text(size: 10.5pt, weight: "bold", tracking: 0.45pt)[#title]
  #v(0.28em)
  #rule()
]

// Same idea for an entry heading: it stays glued to its own bullets.
#let entry-head(body) = block(
  breakable: false,
  sticky: true,
  above: 0.95em,
  below: 0.3em,
)[#body]

#let two-col(left, right) = grid(columns: (1fr, auto), left, right)

// Non-breakable so an entry is never split one bullet on each page.
#let bullets(items) = block(breakable: false, above: 0.3em, below: 0em)[
  #for item in items [
    - #item.text
  ]
]

#let stack-line(items) = {
  let shown = if items.len() > 6 { items.slice(0, 6) } else { items }
  shown.join(", ")
}

#align(center)[
  #text(size: 20pt, weight: "bold")[#p.name]
  #v(0.32em)
  #text(size: 9pt)[
    #link("tel:" + p.phone)[#p.phone]
    | #link("mailto:" + p.email)[#p.email]
    | #link(p.linkedin)[#p.at("linkedin_label", default: "LinkedIn")]
    | #link(p.github)[#p.at("github_label", default: "GitHub")]
    | #link(p.portfolio)[#p.at("portfolio_label", default: "Portfolio")]
  ]
]
#v(0.35em)
#rule()

#section("PROFESSIONAL SUMMARY")
#doc.at("summary", default: "")

#section("PROFESSIONAL EXPERIENCE")
#for role in roles {
  entry-head[
    #two-col(text(weight: "bold")[#role.title], [#role.start – #role.end])
    #two-col(emph[#role.company], emph[#role.location])
  ]
  bullets(role.bullets)
}

#section("SELECTED ENGINEERING PROJECTS")
#for project in projects {
  entry-head[
    #text(weight: "bold")[#project.name]
    #if project.at("stack", default: ()).len() > 0 [
      #text(size: 9.5pt)[ | #stack-line(project.stack)]
    ]
  ]
  bullets(project.bullets)
}

#section("EDUCATION")
#for edu in education {
  block(breakable: false, above: 0.85em, below: 0em)[
    #two-col(text(weight: "bold")[#edu.school], emph[#edu.location])
    #two-col([#edu.credential], [#edu.start – #edu.end])
  ]
}

#section("TECHNICAL EXPERTISE")
#for group in skill-groups [
  - #text(weight: "bold")[#group.label: ]#group.items.join(", ")
]
