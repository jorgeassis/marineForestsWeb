---
layout: page
title: Jaba
permalink: /jaba/
---

Some information about you!

... which is shown in the screenshot below:
![My helpful screenshot]("assets/IMG_3449.jpg")

![_config.yml]({{ site.baseurl }}/images/config.png)

<ul>
  {% for post in site.posts %}
    <li>
      <a href="{{site.baseurl}}{{ post.url }}">{{ post.title }}</a>
      {{ post.excerpt }}
    </li>
  {% endfor %}
</ul>


### More Information

A place to include any other types of information that you'd like to include about yourself.

### Contact me


[email@domain.com](mailto:email@domain.com)
